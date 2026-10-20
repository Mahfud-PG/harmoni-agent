const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers, fetchLatestBaileysVersion, downloadMediaMessage } = require('@whiskeysockets/baileys');
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const pino = require('pino');
const QRCode = require('qrcode');

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(cors());

// Folder DATA bisa berbeda dari folder program saat aplikasi sudah terpasang.
const DATA_ROOT = process.env.HARMONI_DATA_DIR || path.join(__dirname, '..');
const LOG_FILE = path.join(DATA_ROOT, 'wa_bridge.log');

const origLog = console.log;
const origErr = console.error;
console.log = (...args) => {
    origLog.apply(console, args);
    try { fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}][LOG] ` + args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ') + '\n'); } catch(_) {}
};
console.error = (...args) => {
    origErr.apply(console, args);
    try { fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}][ERR] ` + args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ') + '\n'); } catch(_) {}
};
const MULTI_CONFIG = path.join(DATA_ROOT, 'konfigurasi_multi_wa.json');
const LEGACY_AUTH_FOLDER = path.join(DATA_ROOT, 'baileys_auth_info');
const AUTH_ROOT = process.env.HARMONI_WA_AUTH || path.join(DATA_ROOT, 'baileys_auth');
const TEMP_DIR = path.join(DATA_ROOT, 'File', 'Temp');

function pastikanFolder(folder) {
    if (!fs.existsSync(folder)) fs.mkdirSync(folder, { recursive: true });
}
pastikanFolder(AUTH_ROOT);
pastikanFolder(TEMP_DIR);

function bacaKonfigurasiMulti() {
    try {
        if (fs.existsSync(MULTI_CONFIG)) {
            return JSON.parse(fs.readFileSync(MULTI_CONFIG, 'utf8'));
        }
    } catch (e) {
        console.error('[WA Bridge] Gagal membaca konfigurasi_multi_wa.json:', e.message);
    }
    return { active_profile: null, profiles: {} };
}

function daftarProfil() {
    const cfg = bacaKonfigurasiMulti();
    return Object.keys(cfg.profiles || {});
}

function profilAktif() {
    const cfg = bacaKonfigurasiMulti();
    const ids = Object.keys(cfg.profiles || {});
    if (cfg.active_profile && cfg.profiles[cfg.active_profile]) return cfg.active_profile;
    return ids.length ? ids[0] : null;
}

function nomorProfil(profileId) {
    const cfg = bacaKonfigurasiMulti();
    const p = (cfg.profiles || {})[profileId] || {};
    return p.target_phone || '';
}

// ============================================================
// MANAJEMEN SESI GANDA (satu sesi Baileys per profil nomor WA)
// ============================================================
const sessions = new Map(); // profileId -> sesi

function sesiBaru(profileId) {
    return {
        profileId,
        sock: null,
        isReady: false,
        pairingRequested: false,
        pendingPhone: '',
        pairingCode: null,
        hasQrCode: false,
        qrPath: null,
        incomingQueue: [],
        recentMessages: [],
        contactsMap: {},
        myStatuses: [],
        reconnectTimer: null,
        connecting: false
    };
}

function ambilSesi(profileId) {
    const pid = profileId || profilAktif() || 'nomor_1';
    if (!sessions.has(pid)) sessions.set(pid, sesiBaru(pid));
    return sessions.get(pid);
}

function sesiSiap() {
    for (const ses of sessions.values()) {
        if (ses.isReady) return ses;
    }
    return null;
}

function resolveLidToPhone(profileId, lid) {
    if (!lid) return null;
    const cleanLid = lid.toString().replace('@lid', '').replace('@s.whatsapp.net', '').split(':')[0];
    const authDir = path.join(AUTH_ROOT, profileId);
    const fn = path.join(authDir, 'lid-mapping-' + cleanLid + '_reverse.json');
    if (fs.existsSync(fn)) {
        try {
            return JSON.parse(fs.readFileSync(fn, 'utf8'));
        } catch(e) {}
    }
    return null;
}

function formatNomor(nomor, profileId) {
    if (typeof nomor === 'string') {
        nomor = nomor.trim();
        if (nomor.endsWith('@s.whatsapp.net') || nomor.endsWith('@lid') || nomor.endsWith('@g.us')) {
            return nomor;
        }
        let digits = nomor.replace(/[^0-9]/g, '');
        if (digits.length >= 8) {
            let clean = digits;
            if (clean.startsWith('0')) clean = '62' + clean.substring(1);
            return clean + '@s.whatsapp.net';
        }

        // Jika bukan angka (misal nama kontak: "Abiem", "Sulaiman"), cari di contactsMap
        const ses = profileId ? ambilSesi(profileId) : (sesiSiap() || ambilSesi(profilAktif()));
        if (ses && nomor) {
            const q = nomor.toLowerCase();
            for (const c of Object.values(ses.contactsMap)) {
                const nm = (c.name || c.notify || c.verifiedName || '').toLowerCase();
                if (nm && (nm === q || nm.includes(q))) {
                    let phone = resolveLidToPhone(ses.profileId, c.id) || c.id.split('@')[0];
                    if (phone.startsWith('0')) phone = '62' + phone.substring(1);
                    return phone.includes('@') ? phone : (phone + '@s.whatsapp.net');
                }
            }
        }
    }
    return nomor;
}

function bersihkanNomor(phone) {
    let clean = String(phone || '').replace(/[^0-9]/g, '');
    if (clean.startsWith('0')) clean = '62' + clean.substring(1);
    return clean;
}

// Pindahkan sesi lama (satu folder) ke folder profil aktif agar tidak perlu pairing ulang
function migrasiSesiLama() {
    try {
        if (!fs.existsSync(LEGACY_AUTH_FOLDER)) return;
        const pid = profilAktif();
        if (!pid) return;
        const target = path.join(AUTH_ROOT, pid);
        if (fs.existsSync(target)) return;
        fs.renameSync(LEGACY_AUTH_FOLDER, target);
        console.log(`[WA Bridge] Sesi WA lama dipindahkan ke profil '${pid}'.`);
    } catch (e) {
        console.error('[WA Bridge] Gagal migrasi sesi lama:', e.message);
    }
}

async function sambungkanSesi(profileId) {
    const ses = ambilSesi(profileId);
    if (ses.connecting) return ses;
    ses.connecting = true;

    try {
        const authFolder = path.join(AUTH_ROOT, ses.profileId);
        pastikanFolder(authFolder);
        const { state, saveCreds } = await useMultiFileAuthState(authFolder);
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: 'silent' }),
            browser: Browsers.macOS('Desktop'),
            syncFullHistory: false,
            markOnlineOnConnect: true,
            connectTimeoutMs: 60000,
            defaultQueryTimeoutMs: 60000
        });

        ses.sock = sock;
        ses.isReady = false;
        ses.authFolder = authFolder;

        const contactsCacheFile = path.join(authFolder, 'contacts_cache.json');
        if (fs.existsSync(contactsCacheFile)) {
            try {
                ses.contactsMap = Object.assign(ses.contactsMap || {}, JSON.parse(fs.readFileSync(contactsCacheFile, 'utf8')));
            } catch(e) {}
        }

        function simpanContactsCache(s) {
            try {
                const f = path.join(AUTH_ROOT, s.profileId, 'contacts_cache.json');
                fs.writeFileSync(f, JSON.stringify(s.contactsMap, null, 2));
            } catch(e) {}
        }

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('contacts.upsert', (contacts) => {
            for (const c of contacts) {
                ses.contactsMap[c.id] = Object.assign(ses.contactsMap[c.id] || {}, c);
            }
            simpanContactsCache(ses);
        });
        sock.ev.on('contacts.update', (updates) => {
            for (const u of updates) {
                ses.contactsMap[u.id] = Object.assign(ses.contactsMap[u.id] || {}, u);
            }
            simpanContactsCache(ses);
        });

        sock.ev.on('messaging-history.set', ({ contacts, chats }) => {
            if (contacts && Array.isArray(contacts)) {
                for (const c of contacts) {
                    ses.contactsMap[c.id] = Object.assign(ses.contactsMap[c.id] || {}, c);
                }
            }
            if (chats && Array.isArray(chats)) {
                for (const ch of chats) {
                    if (ch.id && (ch.name || ch.notify)) {
                        ses.contactsMap[ch.id] = Object.assign(ses.contactsMap[ch.id] || {}, {
                            id: ch.id,
                            name: ch.name || ch.notify
                        });
                    }
                }
            }
            simpanContactsCache(ses);
            console.log(`[WA Bridge][${ses.profileId}] Sinkronisasi buku kontak (history.set) berhasil: ${Object.keys(ses.contactsMap).length} kontak tersimpan.`);
        });

        sock.ev.on('chats.upsert', (chats) => {
            if (chats && Array.isArray(chats)) {
                for (const ch of chats) {
                    if (ch.id && (ch.name || ch.notify)) {
                        ses.contactsMap[ch.id] = Object.assign(ses.contactsMap[ch.id] || {}, {
                            id: ch.id,
                            name: ch.name || ch.notify
                        });
                    }
                }
                simpanContactsCache(ses);
            }
        });

        sock.ev.on('chats.update', (updates) => {
            if (updates && Array.isArray(updates)) {
                for (const ch of updates) {
                    if (ch.id && (ch.name || ch.notify)) {
                        ses.contactsMap[ch.id] = Object.assign(ses.contactsMap[ch.id] || {}, {
                            id: ch.id,
                            name: ch.name || ch.notify
                        });
                    }
                }
                simpanContactsCache(ses);
            }
        });

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (connection === 'close') {
                const statusCode = (lastDisconnect?.error)?.output?.statusCode;
                // Jangan reconnect jika 401 dan bukan sedang dalam proses pairing
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut && !ses.pairingRequested;
                console.log(`[WA Bridge][${ses.profileId}] Koneksi terputus:`, lastDisconnect?.error?.message, 'statusCode:', statusCode, 'Reconnect:', shouldReconnect);
                ses.isReady = false;
                ses.connecting = false;

                if (shouldReconnect) {
                    if (ses.reconnectTimer) clearTimeout(ses.reconnectTimer);
                    ses.reconnectTimer = setTimeout(() => sambungkanSesi(ses.profileId), 3000);
                } else if (statusCode === DisconnectReason.loggedOut && !ses.pairingRequested) {
                    console.log(`[WA Bridge][${ses.profileId}] LOGGED OUT. Membersihkan auth folder lama untuk pairing ulang...`);
                    try {
                        if (fs.existsSync(ses.authFolder)) {
                            fs.rmSync(ses.authFolder, { recursive: true, force: true });
                        }
                    } catch (e) {}
                }
            } else if (connection === 'open') {
                console.log(`[WA Bridge][${ses.profileId}] WHATSAPP SIAP! Berhasil tersambung.`);
                ses.isReady = true;
                ses.connecting = false;
                ses.pairingRequested = false;
                ses.pairingCode = null;
                const codeFile = path.join(TEMP_DIR, 'KODE_PAIRING_WA.txt');
                if (fs.existsSync(codeFile)) {
                    try { fs.unlinkSync(codeFile); } catch (e) {}
                }
            }

            if (qr && !ses.isReady) {
                try {
                    const qrFilePath = path.join(TEMP_DIR, `QR_CODE_WA_${ses.profileId}.png`);
                    await QRCode.toFile(qrFilePath, qr, {
                        width: 450,
                        margin: 2,
                        color: { dark: '#000000', light: '#ffffff' }
                    });
                    ses.qrPath = qrFilePath;
                    ses.hasQrCode = true;
                    console.log(`[WA Bridge][${ses.profileId}] QR Code disimpan: ${qrFilePath}`);
                } catch (qrErr) {
                    console.error('[WA Bridge] Gagal membuat QR Code PNG:', qrErr.message);
                }

                // Bila ada permintaan pairing code menunggu, minta sekarang
                if (ses.pendingPhone && !ses.pairingRequested) {
                    mintaKodePairing(ses, ses.pendingPhone);
                }
            }
        });

        sock.ev.on('message-receipt.update', (receipts) => {
            if (!Array.isArray(receipts)) return;
            for (const r of receipts) {
                if (r.key?.remoteJid === 'status@broadcast' || !r.key?.remoteJid) {
                    const msgId = r.key?.id;
                    const targetStatus = ses.myStatuses?.find(s => s.id === msgId);
                    if (targetStatus) {
                        const viewerJid = r.receipt?.userJid || r.key?.participant || '';
                        let viewerName = viewerJid.split('@')[0];
                        if (ses.contactsMap?.[viewerJid]?.name) {
                            viewerName = ses.contactsMap[viewerJid].name;
                        }
                        if (viewerName && !targetStatus.viewers.includes(viewerName)) {
                            targetStatus.viewers.push(viewerName);
                            targetStatus.viewerCount = targetStatus.viewers.length;
                        }
                    }
                }
            }
        });

        sock.ev.on('messages.upsert', async (chatUpdate) => {
            try {
                const { messages } = chatUpdate;
                if (!messages || !Array.isArray(messages)) return;

                for (const msg of messages) {
                    if (msg.key?.fromMe) continue;

                    const remoteJid = msg.key?.remoteJid || '';
                    if (!remoteJid || remoteJid === 'status@broadcast' || remoteJid.includes('@broadcast')) continue;
                    if (!msg.message) continue;

                    // ANTI-LOOP: Abaikan pesan yang berasal dari nomor / LID salah satu profil kita sendiri
                    let isFromSelfProfile = false;
                    const jidClean = remoteJid.toLowerCase();
                    for (const s of sessions.values()) {
                        const u = s.sock?.user;
                        if (u) {
                            if (u.id && jidClean.includes(u.id.split(':')[0].toLowerCase())) { isFromSelfProfile = true; break; }
                            if (u.lid && jidClean.includes(u.lid.split(':')[0].toLowerCase())) { isFromSelfProfile = true; break; }
                        }
                        const tp = nomorProfil(s.profileId);
                        if (tp && jidClean.includes(tp.replace(/\D/g, ''))) { isFromSelfProfile = true; break; }
                    }
                    if (isFromSelfProfile) {
                        console.log(`[WA Bridge] Anti-Loop aktif: mengabaikan pesan dari profil sendiri (${remoteJid}) pada profil ${ses.profileId}.`);
                        continue;
                    }

                    const isGroup = remoteJid.endsWith('@g.us');
                    const from = remoteJid.replace('@s.whatsapp.net', '').replace('@g.us', '');
                    const name = msg.pushName || from;

                    let body = '';
                    let isVoiceNote = false;
                    let voicePath = null;

                    const m = msg.message;
                    if (m.conversation) {
                        body = m.conversation;
                    } else if (m.extendedTextMessage?.text) {
                        body = m.extendedTextMessage.text;
                    } else if (m.imageMessage) {
                        body = m.imageMessage.caption || '[Foto]';
                    } else if (m.videoMessage) {
                        body = m.videoMessage.caption || '[Video]';
                    } else if (m.audioMessage) {
                        isVoiceNote = !!m.audioMessage.ptt;
                        body = isVoiceNote ? '[Voice Note]' : '[Audio]';

                        if (!isGroup) {
                            try {
                                const audioBuffer = await downloadMediaMessage(
                                    msg,
                                    'buffer',
                                    {},
                                    {
                                        logger: pino({ level: 'silent' }),
                                        reuploadRequest: ses.sock.updateMediaMessage
                                    }
                                );
                                if (audioBuffer) {
                                    const tempVnPath = path.join(TEMP_DIR, `temp_wa_in_${Date.now()}.ogg`);
                                    fs.writeFileSync(tempVnPath, audioBuffer);
                                    voicePath = tempVnPath;
                                }
                            } catch (dlErr) {
                                console.error('[WA Bridge] Gagal unduh Voice Note:', dlErr.message);
                            }
                        } else {
                            body = '[Voice Note Grup - Dilewati]';
                        }
                    } else if (m.documentMessage) {
                        const fileName = m.documentMessage.fileName || 'file';
                        body = `[Dokumen: ${fileName}]`;
                        try {
                            const docBuffer = await downloadMediaMessage(
                                msg,
                                'buffer',
                                {},
                                {
                                    logger: pino({ level: 'silent' }),
                                    reuploadRequest: ses.sock.updateMediaMessage
                                }
                            );
                            if (docBuffer) {
                                const downloadDir = 'D:\\file hermes';
                                if (!fs.existsSync(downloadDir)) fs.mkdirSync(downloadDir, { recursive: true });
                                const safeName = fileName.replace(/[<>:"/\\|?*]/g, '_');
                                const docPath = path.join(downloadDir, safeName);
                                fs.writeFileSync(docPath, docBuffer);
                                console.log(`[WA Bridge] Berhasil unduh dokumen ke: ${docPath}`);
                            }
                        } catch (dlErr) {
                            console.error('[WA Bridge] Gagal unduh Dokumen:', dlErr.message);
                        }
                    } else if (m.contactMessage) {
                        body = `[Kontak: ${m.contactMessage.displayName || 'kontak'}]`;
                    } else if (m.locationMessage) {
                        body = `[Lokasi: ${m.locationMessage.degreesLatitude}, ${m.locationMessage.degreesLongitude}]`;
                    }

                    if (!body && !voicePath) continue;

                    let finalSenderNum = remoteJid.split('@')[0];
                    if (remoteJid.includes('@lid')) {
                        const resolvedP = resolveLidToPhone(ses.profileId, remoteJid);
                        if (resolvedP) finalSenderNum = resolvedP;
                    }

                    let contactName = name;
                    if ((!contactName || contactName === remoteJid || contactName.includes('@')) && ses.contactsMap) {
                        const c = ses.contactsMap[remoteJid] || ses.contactsMap[finalSenderNum + '@s.whatsapp.net'];
                        if (c && c.name) contactName = c.name;
                    }
                    if (!contactName) contactName = finalSenderNum;

                    const messageData = {
                        id: msg.key?.id,
                        from: remoteJid,
                        senderNumber: finalSenderNum,
                        name: contactName,
                        body: body,
                        isGroup: isGroup,
                        isVoiceNote: isVoiceNote,
                        voicePath: voicePath,
                        profile: ses.profileId,
                        profilePhone: nomorProfil(ses.profileId),
                        timestamp: msg.messageTimestamp ? new Date(Number(msg.messageTimestamp) * 1000).toISOString() : new Date().toISOString()
                    };

                    console.log(`[WA INCOMING][${ses.profileId}] Dari: ${name} (${remoteJid}) | Group: ${isGroup} | Teks: ${body}`);

                    ses.incomingQueue.push(messageData);
                    if (ses.incomingQueue.length > 100) ses.incomingQueue.shift();

                    ses.recentMessages.push(messageData);
                    if (ses.recentMessages.length > 50) ses.recentMessages.shift();
                }
            } catch (err) {
                console.error('[WA Bridge] Error messages.upsert:', err);
            }
        });
    } catch (e) {
        ses.connecting = false;
        console.error(`[WA Bridge][${profileId}] Gagal menyambungkan sesi:`, e.message);
    }

    return ses;
}

async function mintaKodePairing(ses, phone) {
    const cleanPhone = bersihkanNomor(phone);
    ses.pendingPhone = cleanPhone;

    // Bersihkan sesi lama yang korup atau setengah terputus agar socket pairing fresh
    const authFolder = path.join(AUTH_ROOT, ses.profileId);
    if (fs.existsSync(authFolder) && !ses.isReady) {
        try {
            console.log(`[WA Bridge][${ses.profileId}] Membersihkan sisa autentikasi lama sebelum pairing...`);
            if (ses.sock) {
                try { ses.sock.end(undefined); } catch (e) {}
            }
            fs.rmSync(authFolder, { recursive: true, force: true });
            await new Promise(r => setTimeout(r, 1000));
        } catch (e) {}
    }

    // Bangun socket baru yang fresh untuk pairing
    ses.pairingRequested = true;
    await sambungkanSesi(ses.profileId);
    await new Promise(r => setTimeout(r, 2000));

    for (let percobaan = 1; percobaan <= 6; percobaan++) {
        try {
            if (!ses.sock) {
                await sambungkanSesi(ses.profileId);
                await new Promise(r => setTimeout(r, 2000));
            }
            const code = await ses.sock.requestPairingCode(cleanPhone);
            if (code) {
                const kodeFormat = code?.match(/.{1,4}/g)?.join('-') || code;
                ses.pairingCode = kodeFormat;
                ses.pairingRequested = true;
                const kodeFile = path.join(TEMP_DIR, `KODE_PAIRING_WA_${ses.profileId}.txt`);
                fs.writeFileSync(kodeFile, kodeFormat);
                fs.writeFileSync(path.join(TEMP_DIR, 'KODE_PAIRING_WA.txt'), kodeFormat);
                console.log(`\n[WA Bridge][${ses.profileId}] KODE PAIRING: ${kodeFormat}\n`);
                return kodeFormat;
            }
        } catch (err) {
            console.error(`[WA Bridge][${ses.profileId}] Percobaan pairing ke-${percobaan} gagal:`, err.message);
            await new Promise(r => setTimeout(r, 2500));
        }
    }
    return null;
}

// Jalankan semua sesi profil yang sudah punya sesi login sebelumnya
(async () => {
    migrasiSesiLama();
    const ids = daftarProfil();
    if (!ids.length) {
        await sambungkanSesi('nomor_1');
        return;
    }
    for (const pid of ids) {
        const folder = path.join(AUTH_ROOT, pid);
        const legacyBaru = fs.existsSync(folder) && fs.readdirSync(folder).length > 0;
        if (legacyBaru) {
            console.log(`[WA Bridge] Menyambungkan sesi tersimpan untuk profil '${pid}'...`);
            await sambungkanSesi(pid);
        } else {
            console.log(`[WA Bridge] Profil '${pid}' belum tertaut (menunggu kode pairing dari aplikasi).`);
            ambilSesi(pid); // daftarkan sesi kosong
        }
    }
})();

// ============================================================
// REST API
// ============================================================
app.get('/groups', async (req, res) => {
    const target = req.query.profile || 'nomor_1';
    const ses = ambilSesi(target);
    if (!ses || !ses.sock || !ses.ready) {
        return res.status(503).json({ error: 'Sesi WhatsApp tidak siap' });
    }
    try {
        const groups = await ses.sock.groupFetchAllParticipating();
        const list = Object.values(groups).map(g => ({
            id: g.id,
            subject: g.subject,
            desc: g.desc || '',
            participants: g.participants ? g.participants.length : 0
        }));
        res.json(list);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/status', (req, res) => {
    const target = req.query.profile;
    const ringkas = (ses) => ({
        profile: ses.profileId,
        ready: ses.isReady,
        targetPhone: nomorProfil(ses.profileId),
        connectedNumber: ses.sock && ses.sock.user && ses.sock.user.id
            ? ses.sock.user.id.split(':')[0].split('@')[0]
            : null,
        pendingPhone: ses.pendingPhone || null,
        pairingCode: ses.pairingCode || null,
        hasQrCode: !!ses.hasQrCode,
        qrPath: ses.qrPath || null,
        tertaut: ses.isReady
    });

    if (target) {
        return res.json(ringkas(ambilSesi(target)));
    }

    const semua = Array.from(sessions.values()).map(ringkas);
    const siap = sesiSiap();
    res.json({
        ready: !!siap,
        sessions: semua,
        // Kompatibilitas bidang lama
        targetPhone: siap ? nomorProfil(siap.profileId) : (nomorProfil(profilAktif()) || ''),
        pairingCode: siap ? null : (semua.find(s => s.pairingCode)?.pairingCode || null),
        hasQrCode: semua.some(s => s.hasQrCode),
        qrPath: semua.find(s => s.qrPath)?.qrPath || null
    });
});

app.get('/messages', (req, res) => {
    const target = req.query.profile;
    const keluaran = [];
    const daftar = target ? [ambilSesi(target)] : Array.from(sessions.values());
    for (const ses of daftar) {
        keluaran.push(...ses.incomingQueue);
        ses.incomingQueue = [];
    }
    res.json(keluaran);
});

app.get('/unread', (req, res) => {
    const target = req.query.profile;
    const limit = parseInt(req.query.limit, 10) || 10;
    const onlyPrivate = req.query.private_only !== 'false';
    const daftarSesi = target ? [ambilSesi(target)] : Array.from(sessions.values());
    const semua = [];
    for (const ses of daftarSesi) {
        if (!ses) continue;
        for (const m of ses.recentMessages) {
            if (onlyPrivate && m.isGroup) continue;
            semua.push(m);
        }
    }
    // Urutkan dari yang paling baru ke lama
    semua.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    res.json(semua.slice(0, limit));
});

app.get('/contacts', (req, res) => {
    const target = req.query.profile;
    const daftarSesi = target ? [ambilSesi(target)] : Array.from(sessions.values());
    const list = [];
    const seen = new Set();

    for (const ses of daftarSesi) {
        if (!ses) continue;
        for (const c of Object.values(ses.contactsMap)) {
            const rawId = c.id || '';
            let phone = null;
            if (rawId.includes('@s.whatsapp.net')) {
                phone = rawId.split('@')[0].split(':')[0];
            } else if (rawId.includes('@lid')) {
                phone = resolveLidToPhone(ses.profileId, rawId);
            }
            if (!phone && c.phoneNumber) phone = c.phoneNumber;
            const finalPhone = phone || rawId.split('@')[0];
            const name = c.name || c.notify || c.verifiedName || finalPhone || '';
            const key = finalPhone + '_' + name;
            if (finalPhone && !seen.has(key)) {
                seen.add(key);
                list.push({
                    name: name,
                    number: finalPhone,
                    profile: ses.profileId,
                    isPhone: !!phone || finalPhone.startsWith('62') || finalPhone.startsWith('0')
                });
            }
        }
        for (const m of ses.recentMessages) {
            let p = m.senderNumber || '';
            if (p && !p.startsWith('62') && !p.startsWith('0')) {
                p = resolveLidToPhone(ses.profileId, p) || p;
            }
            const key = p + '_' + (m.name || '');
            if (p && !seen.has(key)) {
                seen.add(key);
                list.push({
                    name: m.name || p,
                    number: p,
                    profile: ses.profileId,
                    isPhone: p.startsWith('62') || p.startsWith('0')
                });
            }
        }
    }
    res.json({ status: 'success', contacts: list });
});

app.post('/send', async (req, res) => {
    const { number, message, profile } = req.body;
    const ses = profile ? ambilSesi(profile) : (sesiSiap() || ambilSesi(profilAktif()));
    if (!ses || !ses.isReady) {
        return res.status(503).json({ error: `WhatsApp profil '${profile || 'aktif'}' belum siap/belum tertaut.` });
    }
    try {
        const targetJid = formatNomor(number, ses.profileId);
        await ses.sock.sendMessage(targetJid, { text: message });
        res.json({ success: true, message: 'Terkirim', profile: ses.profileId, targetJid });
    } catch (e) {
        res.status(500).json({ error: e.toString() });
    }
});

const MIME_TYPES = {
    // Audio
    mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', m4a: 'audio/mp4', flac: 'audio/flac',
    mid: 'audio/midi', midi: 'audio/midi', aac: 'audio/aac', wma: 'audio/x-ms-wma',
    // Video
    mp4: 'video/mp4', mkv: 'video/x-matroska', mov: 'video/quicktime', avi: 'video/x-msvideo',
    // Gambar
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif',
    // Dokumen & Proyek DAW
    pdf: 'application/pdf',
    doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ppt: 'application/vnd.ms-powerpoint',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    txt: 'text/plain', zip: 'application/zip', rar: 'application/x-rar-compressed',
    '7z': 'application/x-7z-compressed', rpp: 'application/octet-stream'
};

app.post('/send-media', async (req, res) => {
    const { number, filePath, caption, isVoiceNote, asDocument, profile } = req.body;
    const ses = profile ? ambilSesi(profile) : (sesiSiap() || ambilSesi(profilAktif()));
    if (!ses || !ses.isReady) {
        return res.status(503).json({ error: `WhatsApp profil '${profile || 'aktif'}' belum siap/belum tertaut.` });
    }

    if (!filePath || !fs.existsSync(filePath)) {
        return res.status(404).json({ error: `File media tidak ditemukan: ${filePath}` });
    }

    try {
        const fileName = path.basename(filePath);
        const ext = path.extname(filePath).toLowerCase().replace('.', '');
        const fileBuffer = fs.readFileSync(filePath);
        let mediaParams = {};

        if (isVoiceNote === true) {
            mediaParams = { audio: fileBuffer, mimetype: 'audio/ogg; codecs=opus', ptt: true };
            console.log(`[WA Bridge][${ses.profileId}] Mengirim Voice Note ke ${number}`);
        } else if (asDocument === true || ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'mid', 'midi', 'aac', 'wma'].includes(ext)) {
            mediaParams = {
                document: fileBuffer,
                mimetype: MIME_TYPES[ext] || 'application/octet-stream',
                fileName: fileName,
                caption: caption || ""
            };
            console.log(`[WA Bridge][${ses.profileId}] Mengirim Dokumen ${fileName} (${ext}) ke ${number}`);
        } else if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) {
            mediaParams = { image: fileBuffer, caption: caption || "" };
            console.log(`[WA Bridge][${ses.profileId}] Mengirim Gambar ${fileName} ke ${number}`);
        } else if (['mp4', 'mov', 'mkv', 'avi'].includes(ext)) {
            mediaParams = { video: fileBuffer, caption: caption || "" };
            console.log(`[WA Bridge][${ses.profileId}] Mengirim Video ${fileName} ke ${number}`);
        } else {
            mediaParams = {
                document: fileBuffer,
                mimetype: MIME_TYPES[ext] || 'application/octet-stream',
                fileName: fileName,
                caption: caption || ""
            };
            console.log(`[WA Bridge][${ses.profileId}] Mengirim Dokumen Umum ${fileName} ke ${number}`);
        }

        const targetJid = formatNomor(number, ses.profileId);
        await ses.sock.sendMessage(targetJid, mediaParams);
        res.json({ success: true, message: `Media ${fileName} berhasil terkirim`, profile: ses.profileId, targetJid });
    } catch (e) {
        console.error('[WA Bridge] Gagal kirim media:', e);
        res.status(500).json({ error: e.toString() });
    }
});

// Nomor dianggap sah HANYA jika berbentuk nomor seluler yang masuk akal.
//
// PENTING: satu nomor sampah saja (misal "62029901500080505" yang panjangnya 17
// angka, atau "6256210300408" yang bukan awalan seluler) membuat pencarian
// perangkat di server WhatsApp MENGGANTUNG selamanya. Soketnya lalu tersandera
// dan SEMUA pengiriman berikutnya ikut gagal - bukan hanya status.
// Karena itu penyaringan ini wajib, bukan sekadar kerapian.
function nomorSah(n) {
    if (!n || !/^\d+$/.test(n)) return false;
    // Seluler Indonesia: 628 diikuti 8-11 angka (total 11-13 angka)
    if (/^628[0-9]{8,11}$/.test(n)) return true;
    // Awalan 62 tapi bukan pola seluler (Telkom, kode layanan) -> tolak
    if (n.startsWith('62')) return false;
    // Nomor luar negeri: 11-15 angka, tidak diawali nol
    return /^[1-9][0-9]{10,14}$/.test(n);
}

function rapikanNomor(mentah) {
    let c = String(mentah).replace(/\D/g, '');
    if (c.startsWith('0')) c = '62' + c.slice(1);
    return c;
}

function getStatusRecipients(ses) {
    const list = new Set();
    if (ses.contactsMap) {
        for (const jid of Object.keys(ses.contactsMap)) {
            if (!jid.endsWith('@s.whatsapp.net')) continue;
            const phone = jid.split('@')[0];
            if (nomorSah(phone)) list.add(phone);
        }
    }
    if (Array.isArray(ses.recentMessages)) {
        for (const m of ses.recentMessages) {
            const c = rapikanNomor(m.senderNumber || '');
            if (nomorSah(c)) list.add(c);
        }
    }
    try {
        const kPath = path.join(DATA_ROOT, 'kontak_tersimpan.json');
        if (fs.existsSync(kPath)) {
            const raw = JSON.parse(fs.readFileSync(kPath, 'utf8'));
            for (let num of Object.values(raw)) {
                if (typeof num !== 'string') continue;
                const c = rapikanNomor(num);
                if (nomorSah(c)) list.add(c);
            }
        }
    } catch (_) {}
    return Array.from(list).map(n => n + '@s.whatsapp.net');
}

app.post('/post-status', async (req, res) => {
    const { text, filePath, profile, backgroundColor, font } = req.body;
    console.log(`[WA Bridge] Permintaan /post-status diterima: profile=${profile}, teks="${text?.slice(0, 30)}", file=${filePath}`);
    const ses = profile ? ambilSesi(profile) : (sesiSiap() || ambilSesi(profilAktif()));
    if (!ses || !ses.isReady) {
        console.error(`[WA Bridge] Sesi tidak siap untuk status: ${profile}`);
        return res.status(503).json({ error: `WhatsApp profil '${profile || 'aktif'}' belum siap/belum tertaut.` });
    }
    if (!text && (!filePath || !fs.existsSync(filePath))) {
        return res.status(400).json({ error: 'Harus ada teks atau file media yang valid untuk status.' });
    }

    try {
        console.log(`[WA Bridge][${ses.profileId}] Mengambil daftar kontak untuk status...`);
        const recipients = getStatusRecipients(ses);
        console.log(`[WA Bridge][${ses.profileId}] Total penerima status: ${recipients.length}`);

        let statusContent = {};

        if (filePath && fs.existsSync(filePath)) {
            const ext = path.extname(filePath).toLowerCase().replace('.', '');
            const fileBuffer = fs.readFileSync(filePath);
            if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
                statusContent = { image: fileBuffer, caption: text || '' };
            } else if (['mp4', 'mov', 'mkv'].includes(ext)) {
                statusContent = { video: fileBuffer, caption: text || '' };
            } else if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) {
                statusContent = { audio: fileBuffer, mimetype: 'audio/mp4', ptt: true };
            } else {
                return res.status(400).json({ error: `Format file ${ext} tidak didukung untuk status WhatsApp.` });
            }
        } else {
            const defaultColors = [0xff2e3b4e, 0xff7b1fa2, 0xff1976d2, 0xff388e3c, 0xffd32f2f, 0xff00796b];
            const randColor = defaultColors[Math.floor(Math.random() * defaultColors.length)];
            statusContent = {
                text: text,
                backgroundColor: backgroundColor || randColor,
                font: typeof font === 'number' ? font : 1
            };
        }

        // Daftar penerima: pakai permintaan kalau ada, kalau tidak pakai kontak sah.
        // Keduanya WAJIB disaring - satu nomor sampah cukup untuk menyandera soket.
        let daftarPenerima = [];
        if (Array.isArray(req.body.statusJidList) && req.body.statusJidList.length > 0) {
            daftarPenerima = req.body.statusJidList
                .map(j => String(j).split('@')[0])
                .filter(nomorSah);
        }
        if (daftarPenerima.length === 0) {
            daftarPenerima = recipients;
        }

        const nomorDibuang = recipients.length;
        const sendOptions = {
            statusJidList: daftarPenerima.length > 0 ? daftarPenerima : undefined
        };

        console.log(`[WA Bridge][${ses.profileId}] Mengirim status ke ${daftarPenerima.length} nomor sah (dari ${nomorDibuang} kontak tersimpan)...`);
        const result = await ses.sock.sendMessage('status@broadcast', statusContent, sendOptions);
        console.log(`[WA Bridge][${ses.profileId}] Hasil sendMessage diterima:`, result?.key?.id);

        if (!ses.myStatuses) ses.myStatuses = [];
        const statusItem = {
            id: result?.key?.id || `st_${Date.now()}`,
            timestamp: new Date().toISOString(),
            caption: text || (filePath ? path.basename(filePath) : ''),
            viewers: [],
            viewerCount: 0
        };
        ses.myStatuses.unshift(statusItem);
        if (ses.myStatuses.length > 20) ses.myStatuses = ses.myStatuses.slice(0, 20);

        console.log(`[WA Bridge][${ses.profileId}] Berhasil mengunggah status ke ${daftarPenerima.length} nomor sah.`);
        res.json({
            success: true,
            message: 'Status berhasil diunggah',
            profile: ses.profileId,
            statusId: statusItem.id,
            recipientsCount: daftarPenerima.length
        });
    } catch (e) {
        console.error('[WA Bridge] Gagal unggah status:', e);
        res.status(500).json({ error: e.toString() });
    }
});

app.get('/status-viewers', (req, res) => {
    const pid = req.query.profile || profilAktif() || 'nomor_1';
    const ses = ambilSesi(pid);
    const statuses = ses?.myStatuses || [];
    res.json({
        status: 'success',
        profile: pid,
        totalStatuses: statuses.length,
        statuses: statuses.map(s => ({
            id: s.id,
            caption: s.caption,
            timestamp: s.timestamp,
            viewerCount: s.viewers ? s.viewers.length : 0,
            viewers: s.viewers || []
        }))
    });
});

app.post('/request-pairing', async (req, res) => {
    try {
        const { phone, profile } = req.body;
        if (!phone) return res.status(400).json({ error: 'Nomor telepon wajib diisi.' });
        const pid = profile || profilAktif() || 'nomor_1';
        const ses = ambilSesi(pid);

        console.log(`[WA Bridge][${pid}] Meminta pairing code manual untuk nomor:`, bersihkanNomor(phone));
        if (!ses.sock) {
            await sambungkanSesi(pid);
            await new Promise(r => setTimeout(r, 2500));
        }

        for (let perc = 0; perc < 15; perc++) {
            if (ses.sock && ses.sock.ws?.readyState === 1) break;
            await new Promise(r => setTimeout(r, 500));
        }

        const kode = await mintaKodePairing(ses, phone);
        if (!kode) return res.status(500).json({ error: 'Gagal menghasilkan kode pairing. Coba lagi sebentar.' });

        res.json({ success: true, pairingCode: kode, phone: bersihkanNomor(phone), profile: pid });
    } catch (e) {
        console.error('[WA Bridge] Gagal request pairing code:', e);
        res.status(500).json({ error: e.toString() });
    }
});

app.post('/reset-session', async (req, res) => {
    try {
        const pid = req.body?.profile || profilAktif() || 'nomor_1';
        const ses = ambilSesi(pid);
        console.log(`[WA Bridge][${pid}] Memutuskan koneksi dan mereset sesi WhatsApp...`);

        if (ses.sock) {
            try { ses.sock.end(new Error('Manual disconnect')); } catch (err) {}
        }
        if (ses.reconnectTimer) clearTimeout(ses.reconnectTimer);

        ses.isReady = false;
        ses.pairingRequested = false;
        ses.pairingCode = null;
        ses.pendingPhone = '';
        ses.connecting = false;

        const authFolder = path.join(AUTH_ROOT, pid);
        if (fs.existsSync(authFolder)) fs.rmSync(authFolder, { recursive: true, force: true });

        ['KODE_PAIRING_WA.txt', `KODE_PAIRING_WA_${pid}.txt`, `QR_CODE_WA_${pid}.png`].forEach(f => {
            const p = path.join(TEMP_DIR, f);
            if (fs.existsSync(p)) {
                try { fs.unlinkSync(p); } catch (e) {}
            }
        });

        setTimeout(() => sambungkanSesi(pid), 1500);
        res.json({ success: true, message: `Sesi WhatsApp profil '${pid}' berhasil direset. Silakan tautkan nomor baru.`, profile: pid });
    } catch (e) {
        console.error('[WA Bridge] Gagal reset sesi:', e);
        res.status(500).json({ error: e.toString() });
    }
});

app.post('/connect', async (req, res) => {
    const pid = req.body?.profile || profilAktif() || 'nomor_1';
    const ses = ambilSesi(pid);
    if (!ses.sock) await sambungkanSesi(pid);
    res.json({ success: true, profile: pid, ready: ses.isReady });
});

app.listen(3000, () => {
    console.log('Harmoni WA Bridge (Baileys Multi-Sesi) API listening on port 3000');
});
