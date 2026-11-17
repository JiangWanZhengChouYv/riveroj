/**
 * oj-judge 健康检查（在 judge 容器内运行，只读挂载，不改镜像）。
 *
 * 判据：judge daemon 与 backend 之间是长连接。backend 重启后连接断开且
 * judge 不会自动重连；/status 里 stats[type=judge].updateAt 只在连接建立时
 * 上报一次，不是持续心跳，不能用来判活。因此：
 *   1) 先用 HTTP /status 确认 backend 已就绪（不可达只标记 unhealthy，不重启）；
 *   2) 再读 /proc/net/tcp{,6}，看有没有到 backend:8888 的 ESTABLISHED(01) 连接。
 *
 * 退出码：
 *   0 = 健康（长连接存在）
 *   1 = backend 暂时不可达 / 数据异常（不重启容器，避免 backend 重启期间抖动）
 *   2 = judge 确实断连（compose healthcheck 据此 SIGKILL PID 1，restart: always 拉起重连）
 */
const http = require('http');
const fs = require('fs');

const HOST = process.env.OJ_BACKEND_HOST || 'oj-backend';
const PORT = Number(process.env.OJ_BACKEND_PORT || 8888);
const TIMEOUT_MS = 4000;

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/** backend 是否就绪；请求带 Connection: close，读完后连接不会保持 ESTABLISHED */
function backendReady() {
    return new Promise((resolve, reject) => {
        const req = http.get({
            host: HOST,
            port: PORT,
            path: '/status',
            headers: { Accept: 'application/json', Connection: 'close' },
            timeout: TIMEOUT_MS,
        }, (res) => {
            res.resume();
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 400) resolve();
                else reject(new Error(`HTTP ${res.statusCode}`));
            });
        });
        req.on('timeout', () => req.destroy(new Error('请求超时')));
        req.on('error', reject);
    });
}

/** 找到 PM2 管理的 hydrojudge 子进程（排除 pm2-runtime 与健康检查自己） */
function findJudgePid() {
    let entries = [];
    try { entries = fs.readdirSync('/proc').filter((x) => /^\d+$/.test(x)); } catch { return null; }
    for (const pid of entries) {
        let cmd = '';
        try { cmd = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').replace(/\0/g, ' ').trim(); } catch { continue; }
        if (cmd.includes('/usr/local/bin/hydrojudge')
            && !cmd.includes('pm2-runtime')
            && !cmd.includes('judge-healthcheck')) return Number(pid);
    }
    return null;
}

/** /proc/net/tcp 里是否存在到 backend:8888 的 ESTABLISHED（状态 01）连接 */
function hasJudgeConnection() {
    for (const file of ['/proc/net/tcp', '/proc/net/tcp6']) {
        let text = '';
        try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }
        for (const line of text.trim().split('\n').slice(1)) {
            const parts = line.trim().split(/\s+/);
            const remotePort = parseInt((parts[2] || '').split(':')[1] || '0', 16);
            const state = (parts[3] || '').toUpperCase();
            if (remotePort === PORT && state === '01') return true;
        }
    }
    return false;
}

(async () => {
    try {
        await backendReady();
    } catch (e) {
        // backend 正在重启：不要动 judge，等它回来
        console.error(`judge healthcheck: backend unavailable (${e.message})`);
        process.exit(1);
    }
    // 让上面那个请求的连接彻底离开 ESTABLISHED（进入 TIME_WAIT）
    await sleep(200);
    if (hasJudgeConnection()) {
        console.log('judge healthcheck: connected to backend');
        process.exit(0);
    }
    console.error('judge healthcheck: judge daemon disconnected from backend');
    // 容器内 PID 1 受内核保护杀不动；改杀 PM2 管着的 hydrojudge 子进程，
    // PM2 God Daemon 会自动把它拉起并重新连接 backend。
    const pid = findJudgePid();
    if (pid) {
        try {
            process.kill(pid, 'SIGKILL');
            console.error(`judge healthcheck: killed hydrojudge pid ${pid} (PM2 will restart it)`);
        } catch (e) {
            console.error(`judge healthcheck: kill hydrojudge failed: ${e.message}`);
        }
    } else {
        console.error('judge healthcheck: hydrojudge process not found');
    }
    process.exit(2);
})();
