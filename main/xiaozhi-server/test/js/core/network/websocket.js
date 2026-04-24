// WebSocket消息处理模块
import { getConfig, saveConnectionUrls } from '../../config/manager.js?v=0205';
import { uiController } from '../../ui/controller.js?v=0205';
import { log } from '../../utils/logger.js?v=0205';
import { getAudioPlayer } from '../audio/player.js?v=0205';
import { getAudioRecorder } from '../audio/recorder.js?v=0205';
import { executeMcpTool, getMcpTools, setWebSocket as setMcpWebSocket } from '../mcp/tools.js?v=0205';
import { webSocketConnect } from './ota-connector.js?v=0205';

// WebSocket处理器类
export class WebSocketHandler {
    constructor() {
        this.websocket = null;
        this.onConnectionStateChange = null;
        this.onRecordButtonStateChange = null;
        this.onSessionStateChange = null;
        this.onSessionEmotionChange = null;
        this.onChatMessage = null; // 新增：聊天消息回调
        this.currentSessionId = null;
        this.isRemoteSpeaking = false;
    }

    // 发送hello握手消息
    async sendHelloMessage() {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) return false;

        try {
            const config = getConfig();

            const helloMessage = {
                type: 'hello',
                device_id: config.deviceId,
                device_name: config.deviceName,
                device_mac: config.deviceMac,
                token: config.token,
                features: {
                    mcp: true
                }
            };

            log('Gửi tin nhắn bắt tay hello', 'info');
            this.websocket.send(JSON.stringify(helloMessage));

            return new Promise(resolve => {
                const timeout = setTimeout(() => {
                    log('Hết thời gian chờ phản hồi hello', 'error');
                    log('Gợi ý: Vui lòng thử nhấn nút "Kiểm tra xác thực" để kiểm tra kết nối', 'info');
                    resolve(false);
                }, 5000);

                const onMessageHandler = (event) => {
                    try {
                        const response = JSON.parse(event.data);
                        if (response.type === 'hello' && response.session_id) {
                            log(`Bắt tay server thành công, ID phiên: ${response.session_id}`, 'success');
                            clearTimeout(timeout);
                            this.websocket.removeEventListener('message', onMessageHandler);
                            resolve(true);
                        }
                    } catch (e) {
                        // Bỏ qua tin nhắn không phải JSON
                    }
                };

                this.websocket.addEventListener('message', onMessageHandler);
            });
        } catch (error) {
            log(`Lỗi gửi tin nhắn hello: ${error.message}`, 'error');
            return false;
        }
    }

    // 处理文本消息
    handleTextMessage(message) {
        if (message.type === 'hello') {
            log(`Phản hồi server：${JSON.stringify(message, null, 2)}`, 'success');
            window.cameraAvailable = true;
            log('Kết nối thành công, camera đã sẵn sàng', 'success');
            uiController.updateDialButton(true);
            uiController.startAIChatSession();
        } else if (message.type === 'tts') {
            this.handleTTSMessage(message);
        } else if (message.type === 'audio') {
            log(`Nhận tin nhắn điều khiển âm thanh: ${JSON.stringify(message)}`, 'info');
        } else if (message.type === 'stt') {
            log(`Kết quả nhận dạng: ${message.text}`, 'info');
            // 检查是否需要绑定设备
            if (message.text && (message.text.includes('绑定') || message.text.includes('bind'))) {
                log('Nhận yêu cầu liên kết thiết bị, cập nhật trạng thái camera', 'warning');
                window.cameraAvailable = false;
                // 关闭摄像头
                if (typeof window.stopCamera === 'function') {
                    window.stopCamera();
                }
                // 更新摄像头按钮状态
                const cameraBtn = document.getElementById('cameraBtn');
                if (cameraBtn) {
                    cameraBtn.classList.remove('camera-active');
                    cameraBtn.querySelector('.btn-text').textContent = 'Camera';
                    cameraBtn.disabled = true;
                    cameraBtn.title = 'Vui lòng liên kết mã xác nhận trước';
                }
            }
            // 使用新的聊天消息回调显示STT消息
            if (this.onChatMessage && message.text) {
                this.onChatMessage(message.text, true);
            }
        } else if (message.type === 'llm') {
            log(`Phản hồi LLM: ${message.text}`, 'info');
            // 使用新的聊天消息回调显示LLM回复
            if (this.onChatMessage && message.text) {
                this.onChatMessage(message.text, false);
            }

            // 如果包含表情，更新sessionStatus表情并触发Live2D动作
            if (message.text && /[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/u.test(message.text)) {
                // 提取表情符号
                const emojiMatch = message.text.match(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/u);
                if (emojiMatch && this.onSessionEmotionChange) {
                    this.onSessionEmotionChange(emojiMatch[0]);
                }

                // 触发Live2D情绪动作
                if (message.emotion) {
                    console.log(`Nhận tin nhắn cảm xúc: emotion=${message.emotion}, text=${message.text}`);
                    this.triggerLive2DEmotionAction(message.emotion);
                }
            }

            // 只有当文本不仅仅是表情时，才添加到对话中
            // 移除文本中的表情后检查是否还有内容
            const textWithoutEmoji = message.text ? message.text.replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/gu, '').trim() : '';
            if (textWithoutEmoji && this.onChatMessage) {
                this.onChatMessage(message.text, false);
            }
        } else if (message.type === 'mcp') {
            this.handleMCPMessage(message);
        } else {
            log(`Loại tin nhắn không xác định: ${message.type}`, 'info');
            if (this.onChatMessage) {
                this.onChatMessage(`Loại tin nhắn không xác định: ${message.type}\n${JSON.stringify(message, null, 2)}`, false);
            }
        }
    }

    // 处理TTS消息
    handleTTSMessage(message) {
        if (message.state === 'start') {
            log('Server bắt đầu gửi giọng nói', 'info');
            this.currentSessionId = message.session_id;
            this.isRemoteSpeaking = true;
            if (this.onSessionStateChange) {
                this.onSessionStateChange(true);
            }

            // 启动Live2D说话动画
            this.startLive2DTalking();
        } else if (message.state === 'sentence_start') {
            log(`Server gửi đoạn thoại: ${message.text}`, 'info');
            this.ttsSentenceCount = (this.ttsSentenceCount || 0) + 1;

            if (message.text && this.onChatMessage) {
                this.onChatMessage(message.text, false);
            }

            // 确保动画在句子开始时运行
            const live2dManager = window.chatApp?.live2dManager;
            if (live2dManager && !live2dManager.isTalking) {
                this.startLive2DTalking();
            }
        } else if (message.state === 'sentence_end') {
            log(`Kết thúc đoạn thoại: ${message.text}`, 'info');

            // 句子结束时不清除动画，等待下一个句子或最终停止
        } else if (message.state === 'stop') {
            log('Kết thúc truyền giọng nói từ máy chủ, xóa tất cả bộ đệm âm thanh', 'info');

            // 清空所有音频缓冲并停止播放
            const audioPlayer = getAudioPlayer();
            audioPlayer.clearAllAudio();

            this.isRemoteSpeaking = false;
            if (this.onRecordButtonStateChange) {
                this.onRecordButtonStateChange(false);
            }
            if (this.onSessionStateChange) {
                this.onSessionStateChange(false);
            }

            // 延迟停止Live2D说话动画，确保所有句子都播放完毕
            setTimeout(() => {
                this.stopLive2DTalking();
                this.ttsSentenceCount = 0; // 重置计数器
            }, 1000); // 1秒延迟，确保所有句子都完成
        }
    }

    // 启动Live2D说话动画
    startLive2DTalking() {
        try {
            // 获取Live2D管理器实例
            const live2dManager = window.chatApp?.live2dManager;
            if (live2dManager && live2dManager.live2dModel) {
                // 使用音频播放器的分析器节点
                live2dManager.startTalking();
                log('Đã bắt đầu hoạt ảnh nói Live2D', 'info');
            }
        } catch (error) {
            log(`Khởi động hoạt ảnh nói Live2D thất bại: ${error.message}`, 'error');
        }
    }

    // 停止Live2D说话动画
    stopLive2DTalking() {
        try {
            const live2dManager = window.chatApp?.live2dManager;
            if (live2dManager) {
                live2dManager.stopTalking();
                log('Đã dừng hoạt ảnh nói Live2D', 'info');
            }
        } catch (error) {
            log(`Dừng hoạt ảnh nói Live2D thất bại: ${error.message}`, 'error');
        }
    }

    // 初始化Live2D音频分析器
    initializeLive2DAudioAnalyzer() {
        try {
            const live2dManager = window.chatApp?.live2dManager;
            if (live2dManager) {
                // 初始化音频分析器（使用音频播放器的上下文）
                if (live2dManager.initializeAudioAnalyzer()) {
                    log('Khởi tạo phân tích âm thanh Live2D hoàn tất, đã kết nối với máy phát âm thanh', 'success');
                } else {
                    log('Khởi tạo phân tích âm thanh Live2D thất bại, sẽ sử dụng hoạt ảnh mô phỏng', 'warning');
                }
            }
        } catch (error) {
            log(`Khởi tạo phân tích âm thanh Live2D thất bại: ${error.message}`, 'error');
        }
    }

    // 处理MCP消息
    handleMCPMessage(message) {
        const payload = message.payload || {};
        log(`Server gửi: ${JSON.stringify(message)}`, 'info');

        if (payload.method === 'tools/list') {
            const tools = getMcpTools();

            const replyMessage = JSON.stringify({
                "session_id": message.session_id || "",
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "result": {
                        "tools": tools
                    }
                }
            });
            log(`Báo cáo client: ${replyMessage}`, 'info');
            this.websocket.send(replyMessage);
            log(`Phản hồi danh sách công cụ MCP: ${tools.length} công cụ`, 'info');

        } else if (payload.method === 'tools/call') {
            const toolName = payload.params?.name;
            const toolArgs = payload.params?.arguments;

            log(`Gọi công cụ: ${toolName} Tham số: ${JSON.stringify(toolArgs)}`, 'info');

            executeMcpTool(toolName, toolArgs).then(result => {
                const replyMessage = JSON.stringify({
                    "session_id": message.session_id || "",
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "id": payload.id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": JSON.stringify(result)
                                }
                            ],
                            "isError": false
                        }
                    }
                });

                log(`Báo cáo client: ${replyMessage}`, 'info');
                this.websocket.send(replyMessage);
            }).catch(error => {
                log(`Thực thi công cụ thất bại: ${error.message}`, 'error');
                const errorReply = JSON.stringify({
                    "session_id": message.session_id || "",
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "id": payload.id,
                        "error": {
                            "code": -32603,
                            "message": error.message
                        }
                    }
                });
                this.websocket.send(errorReply);
            });
        } else if (payload.method === 'initialize') {
            log(`Nhận yêu cầu khởi tạo công cụ: ${JSON.stringify(payload.params)}`, 'info');
            // 保存视觉分析接口地址
            const visionUrl = document.getElementById('visionUrl');
            const visionConfig = payload?.params?.capabilities?.vision;
            if (visionConfig && typeof visionConfig === 'object' && visionConfig.url && visionConfig.token) {
                const visionConfigStr = JSON.stringify(visionConfig);
                localStorage.setItem('xz_tester_vision', visionConfigStr);
                if (visionUrl) visionUrl.value = visionConfig.url;
            } else {
                localStorage.removeItem('xz_tester_vision');
                if (visionUrl) visionUrl.value = '';
            }

            const replyMessage = JSON.stringify({
                "session_id": message.session_id || "",
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "xiaozhi-web-test",
                            "version": "2.1.0"
                        }
                    }
                }
            });
            log(`Phản hồi khởi tạo`, 'info');
            this.websocket.send(replyMessage);
        } else {
            log(`Phương thức MCP không xác định: ${payload.method}`, 'warning');
        }
    }

    // 处理二进制消息
    async handleBinaryMessage(data) {
        try {
            let arrayBuffer;
            if (data instanceof ArrayBuffer) {
                arrayBuffer = data;
            } else if (data instanceof Blob) {
                arrayBuffer = await data.arrayBuffer();
                log(`Nhận dữ liệu âm thanh Blob, kích thước: ${arrayBuffer.byteLength} byte`, 'debug');
            } else {
                log(`Nhận loại dữ liệu nhị phân không xác định: ${typeof data}`, 'warning');
                return;
            }

            const opusData = new Uint8Array(arrayBuffer);
            const audioPlayer = getAudioPlayer();
            audioPlayer.enqueueAudioData(opusData);
        } catch (error) {
            log(`Xử lý tin nhắn nhị phân thất bại: ${error.message}`, 'error');
        }
    }

    // 连接WebSocket服务器
    async connect() {
        const config = getConfig();
        log('Đang kiểm tra trạng thái OTA...', 'info');
        saveConnectionUrls();

        try {
            const otaUrl = document.getElementById('otaUrl').value.trim();
            const ws = await webSocketConnect(otaUrl, config);
            if (ws === undefined) {
                return false;
            }
            this.websocket = ws;

            // 设置接收二进制数据的类型为ArrayBuffer
            this.websocket.binaryType = 'arraybuffer';

            // 设置 MCP 模块的 WebSocket 实例
            setMcpWebSocket(this.websocket);

            // 设置录音器的WebSocket
            const audioRecorder = getAudioRecorder();
            audioRecorder.setWebSocket(this.websocket);

            this.setupEventHandlers();

            return true;
        } catch (error) {
            log(`Lỗi kết nối: ${error.message}`, 'error');
            if (this.onConnectionStateChange) {
                this.onConnectionStateChange(false);
            }
            return false;
        }
    }

    // 设置事件处理器
    setupEventHandlers() {
        this.websocket.onopen = async () => {
            const url = document.getElementById('serverUrl').value;
            log(`Đã kết nối với máy chủ: ${url}`, 'success');

            if (this.onConnectionStateChange) {
                this.onConnectionStateChange(true);
            }

            // 连接成功后，默认状态为聆听中
            this.isRemoteSpeaking = false;
            if (this.onSessionStateChange) {
                this.onSessionStateChange(false);
            }

            // 在WebSocket连接成功时初始化Live2D音频分析器
            this.initializeLive2DAudioAnalyzer();

            await this.sendHelloMessage();
        };

        this.websocket.onclose = () => {
            log('Đã ngắt kết nối', 'info');

            if (this.onConnectionStateChange) {
                this.onConnectionStateChange(false);
            }

            const audioRecorder = getAudioRecorder();
            audioRecorder.stop();

            // 关闭摄像头
            if (typeof window.stopCamera === 'function') {
                window.stopCamera();
            }

            // 隐藏摄像头显示区域
            const cameraContainer = document.getElementById('cameraContainer');
            if (cameraContainer) {
                cameraContainer.classList.remove('active');
            }
        };

        this.websocket.onerror = (error) => {
            log(`Lỗi WebSocket: ${error.message || 'Lỗi không xác định'}`, 'error');
            uiController.addChatMessage(`⚠️ Lỗi WebSocket: ${error.message || 'Lỗi không xác định'}`, false);
            if (this.onConnectionStateChange) {
                this.onConnectionStateChange(false);
            }
        };

        this.websocket.onmessage = (event) => {
            try {
                if (typeof event.data === 'string') {
                    const message = JSON.parse(event.data);
                    this.handleTextMessage(message);
                } else {
                    this.handleBinaryMessage(event.data);
                }
            } catch (error) {
                log(`Lỗi xử lý tin nhắn WebSocket: ${error.message}`, 'error');
                // 不再使用旧的addMessage函数，因为conversationDiv元素不存在
                // 错误消息将通过其他方式显示
            }
        };
    }

    // 断开连接
    disconnect() {
        if (!this.websocket) return;

        this.websocket.close();
        const audioRecorder = getAudioRecorder();
        audioRecorder.stop();

        // 关闭摄像头
        if (typeof window.stopCamera === 'function') {
            window.stopCamera();
        }

        // 隐藏摄像头显示区域
        const cameraContainer = document.getElementById('cameraContainer');
        if (cameraContainer) {
            cameraContainer.classList.remove('active');
        }
    }

    // 发送文本消息
    sendTextMessage(text) {
        if (text === '' || !this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            return false;
        }

        try {
            // 如果对方正在说话，先发送打断消息
            if (this.isRemoteSpeaking && this.currentSessionId) {
                const abortMessage = {
                    session_id: this.currentSessionId,
                    type: 'abort',
                    reason: 'wake_word_detected'
                };
                this.websocket.send(JSON.stringify(abortMessage));
                log('Gửi tin nhắn ngắt lời', 'info');
            }

            const listenMessage = {
                type: 'listen',
                state: 'detect',
                text: text
            };

            this.websocket.send(JSON.stringify(listenMessage));
            log(`Gửi tin nhắn văn bản: ${text}`, 'info');

            return true;
        } catch (error) {
            log(`Lỗi gửi tin nhắn: ${error.message}`, 'error');
            return false;
        }
    }

    /**
     * 触发Live2D情绪动作
     * @param {string} emotion - 情绪名称
     */
    triggerLive2DEmotionAction(emotion) {
        try {
            const live2dManager = window.chatApp?.live2dManager;
            if (live2dManager && typeof live2dManager.triggerEmotionAction === 'function') {
                live2dManager.triggerEmotionAction(emotion);
                log(`Kích hoạt hoạt ảnh cảm xúc Live2D: ${emotion}`, 'info');
            } else {
                log(`Không thể kích hoạt hoạt ảnh cảm xúc Live2D: Không tìm thấy quản lý Live2D hoặc phương thức không khả dụng`, 'warning');
            }
        } catch (error) {
            log(`Kích hoạt hoạt ảnh cảm xúc Live2D thất bại: ${error.message}`, 'error');
        }
    }

    // 获取WebSocket实例
    getWebSocket() {
        return this.websocket;
    }

    // 检查是否已连接
    isConnected() {
        return this.websocket && this.websocket.readyState === WebSocket.OPEN;
    }
}

// 创建单例
let wsHandlerInstance = null;

export function getWebSocketHandler() {
    if (!wsHandlerInstance) {
        wsHandlerInstance = new WebSocketHandler();
    }
    return wsHandlerInstance;
}
