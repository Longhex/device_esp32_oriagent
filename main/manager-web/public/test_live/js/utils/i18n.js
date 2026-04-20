const translations = {
    'vi': {
        'title': 'Trang Kiểm tra Máy chủ Xiaozhi',
        'offline': 'Ngoại tuyến',
        'online': 'Trực tuyến',
        'dialing': 'Đang gọi...',
        'connected': 'Đã kết nối',
        'disconnected': 'Đã ngắt kết nối',
        'modelLoading': 'Đang tải mô hình... ✨',
        'inputPlaceholder': 'Nhập tin nhắn, nhấn Enter để gửi',
        'settings': 'Cài đặt',
        'camera': 'Máy ảnh',
        'dial': 'Gọi',
        'hangup': 'Gác máy',
        'record': 'Ghi âm',
        'deviceConfig': 'Cấu hình thiết bị',
        'mcpTools': 'Công cụ MCP',
        'avatarSkin': 'Da nhân vật',
        'deviceMac': 'MAC thiết bị:',
        'clientId': 'ID khách:',
        'deviceName': 'Tên thiết bị:',
        'otaAddress': 'Địa chỉ máy chủ OTA:',
        'wsAddress': 'Địa chỉ WebSocket:',
        'visionAddress': 'Địa chỉ phân tích thị giác:',
        'close': 'Đóng',
        'save': 'Lưu',
        'cancel': 'Hủy',
        'addTool': '➕ Thêm công cụ mới'
    },
    'en': {
        'title': 'Xiaozhi Server Test Page',
        'offline': 'Offline',
        'online': 'Online',
        'dialing': 'Dialing...',
        'connected': 'Connected',
        'disconnected': 'Disconnected',
        'modelLoading': 'Model Loading... ✨',
        'inputPlaceholder': 'Enter message, press Enter to send',
        'settings': 'Settings',
        'camera': 'Camera',
        'dial': 'Dial',
        'hangup': 'Hang up',
        'record': 'Record',
        'deviceConfig': 'Device Config',
        'mcpTools': 'MCP Tools',
        'avatarSkin': 'Digital Avatar',
        'deviceMac': 'Device MAC:',
        'clientId': 'Client ID:',
        'deviceName': 'Device Name:',
        'otaAddress': 'OTA Server URL:',
        'wsAddress': 'WebSocket URL:',
        'visionAddress': 'Vision Analysis URL:',
        'close': 'Close',
        'save': 'Save',
        'cancel': 'Cancel',
        'addTool': '➕ Add New Tool'
    },
    'zh': {
        'title': '小智服务器测试页面',
        'offline': '离线',
        'online': '在线',
        'dialing': '呼叫中...',
        'connected': '已连接',
        'disconnected': '已断开',
        'modelLoading': '模型加载中... ✨',
        'inputPlaceholder': '输入消息, 按Enter发送',
        'settings': '设置',
        'camera': '摄像头',
        'dial': '拨号',
        'hangup': '挂断',
        'record': '录音',
        'deviceConfig': '设备配置',
        'mcpTools': 'MCP工具',
        'avatarSkin': '数字人皮肤',
        'deviceMac': '设备MAC:',
        'clientId': '客户端ID:',
        'deviceName': '设备名称:',
        'otaAddress': 'OTA服务器地址:',
        'wsAddress': 'WebSocket服务器地址:',
        'visionAddress': '视觉分析地址:',
        'close': '关闭',
        'save': '保存',
        'cancel': '取消',
        'addTool': '➕ 添加新工具'
    }
};

function getQueryParams() {
    const params = {};
    window.location.search.substring(1).split('&').forEach(pair => {
        const [key, value] = pair.split('=');
        if (key) params[key] = decodeURIComponent(value);
    });
    return params;
}

function initI18n() {
    const params = getQueryParams();
    let lang = params.lang || 'zh';
    if (lang.startsWith('vi')) lang = 'vi';
    else if (lang.startsWith('en')) lang = 'en';
    else lang = 'zh';

    const t = translations[lang];

    // Update title
    document.title = t.title;

    // Selection by ID
    const elements = {
        'connectionStatus': t.offline,
        'modelLoading': t.modelLoading,
        'messageInput': 'placeholder:' + t.inputPlaceholder,
        'settingsBtn': 'title:' + t.settings,
        'cameraBtn': 'title:' + t.camera,
        'dialBtn': 'title:' + t.dial,
        'recordBtn': 'title:' + t.record,
    };

    // Update defined IDs
    for (const [id, value] of Object.entries(elements)) {
        const el = document.getElementById(id);
        if (el) {
            if (value.startsWith('placeholder:')) {
                el.placeholder = value.split(':')[1];
            } else if (value.startsWith('title:')) {
                el.title = value.split(':')[1];
            } else {
                el.innerText = value;
            }
        }
    }

    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (t[key]) {
            if (el.tagName === 'INPUT' && el.type === 'text') {
                el.placeholder = t[key];
            } else {
                el.innerText = t[key];
            }
        }
    });

    window.t = t;
    return t;
}

window.initI18n = initI18n;
