// 配置管理模块

// 生成随机MAC地址
function generateRandomMac() {
    const hexDigits = '0123456789ABCDEF';
    let mac = '';
    for (let i = 0; i < 6; i++) {
        if (i > 0) mac += ':';
        for (let j = 0; j < 2; j++) {
            mac += hexDigits.charAt(Math.floor(Math.random() * 16));
        }
    }
    return mac;
}

// 加载配置
export function loadConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');
    const otaUrlInput = document.getElementById('otaUrl');

    // 解析URL参数
    const urlParams = new URLSearchParams(window.location.search);
    const agentId = urlParams.get('agentId');
    const queryOtaUrl = urlParams.get('otaUrl');

    // 优先从URL获取MAC地址，但是要注意如果agentId被传进来，它是一个UUID而不是MAC，不能直接用作MAC地址
    // 修复OTA连接失败：不把agentId作为MAC地址
    // Ưu tiên MAC test RIÊNG theo agent (truyền từ trang quản lý qua tham số deviceMac) -> mỗi agent 1 MAC,
    // tránh việc mọi agent dùng chung 1 MAC trong localStorage. KHÔNG ghi đè key chung để không ảnh hưởng dùng độc lập.
    const queryMac = urlParams.get('deviceMac');
    let savedMac;
    if (queryMac && queryMac.includes(':')) {
        savedMac = queryMac;
    } else {
        savedMac = localStorage.getItem('xz_tester_deviceMac');
        // 如果保存的MAC地址格式不对（比如之前错误地保存了UUID），则重新生成
        if (!savedMac || !savedMac.includes(':')) {
            savedMac = generateRandomMac();
            localStorage.setItem('xz_tester_deviceMac', savedMac);
        }
    }
    deviceMacInput.value = savedMac;

    // 优先从URL获取OTA URL
    const savedOtaUrl = queryOtaUrl || localStorage.getItem('xz_tester_otaUrl');
    if (savedOtaUrl) {
        otaUrlInput.value = savedOtaUrl;
    }

    // 从localStorage加载其他配置
    const savedDeviceName = localStorage.getItem('xz_tester_deviceName');
    if (savedDeviceName) {
        deviceNameInput.value = savedDeviceName;
    }

    const savedClientId = localStorage.getItem('xz_tester_clientId');
    if (savedClientId) {
        clientIdInput.value = savedClientId;
    }
}

// 保存配置
export function saveConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');

    localStorage.setItem('xz_tester_deviceMac', deviceMacInput.value);
    localStorage.setItem('xz_tester_deviceName', deviceNameInput.value);
    localStorage.setItem('xz_tester_clientId', clientIdInput.value);
}

// 获取配置值
export function getConfig() {
    // 从DOM获取值
    const deviceMac = document.getElementById('deviceMac')?.value.trim() || '';
    const deviceName = document.getElementById('deviceName')?.value.trim() || '';
    const clientId = document.getElementById('clientId')?.value.trim() || '';

    return {
        deviceId: deviceMac,  // 使用MAC地址作为deviceId
        deviceName,
        deviceMac,
        clientId
    };
}

// 保存连接URL
export function saveConnectionUrls() {
    const otaUrl = document.getElementById('otaUrl').value.trim();
    const wsUrl = document.getElementById('serverUrl').value.trim();
    localStorage.setItem('xz_tester_otaUrl', otaUrl);
    localStorage.setItem('xz_tester_wsUrl', wsUrl);
}
