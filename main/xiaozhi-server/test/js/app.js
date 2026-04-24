// 主应用入口
import { checkOpusLoaded, initOpusEncoder } from './core/audio/opus-codec.js?v=0205';
import { getAudioPlayer } from './core/audio/player.js?v=0205';
import { checkMicrophoneAvailability, isHttpNonLocalhost } from './core/audio/recorder.js?v=0205';
import { initMcpTools } from './core/mcp/tools.js?v=0205';
import { uiController } from './ui/controller.js?v=0205';
import { log } from './utils/logger.js?v=0205';

// 辅助函数：将Base64数据转换为Blob
function dataURItoBlob(dataURI) {
    const byteString = atob(dataURI.split(',')[1]);
    const mimeString = dataURI.split(',')[0].split(':')[1].split(';')[0];
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteString.length; i++) {
        ia[i] = byteString.charCodeAt(i);
    }
    return new Blob([ab], { type: mimeString });
}

// 应用类
class App {
    constructor() {
        this.uiController = null;
        this.audioPlayer = null;
        this.live2dManager = null;
        this.cameraStream = null;
        this.currentFacingMode = 'user';
    }

    // 初始化应用
    async init() {
        log('Đang khởi tạo ứng dụng...', 'info');
        // 初始化UI控制器
        this.uiController = uiController;
        this.uiController.init();
        // 检查Opus库
        checkOpusLoaded();
        // 初始化Opus编码器
        initOpusEncoder();
        // 初始化音频播放器
        this.audioPlayer = getAudioPlayer();
        await this.audioPlayer.start();
        // 初始化MCP工具
        initMcpTools();
        // 检查麦克风可用性
        await this.checkMicrophoneAvailability();
        // 检查摄像头可用性
        this.checkCameraAvailability();
        // 初始化Live2D
        await this.initLive2D();
        // 初始化摄像头
        this.initCamera();
        // 关闭加载loading
        this.setModelLoadingStatus(false);
        log('Khởi tạo ứng dụng hoàn tất', 'success');
    }

    // 初始化Live2D
    async initLive2D() {
        try {
            // 检查Live2DManager是否已加载
            if (typeof window.Live2DManager === 'undefined') {
                throw new Error('Live2DManager chưa được tải, vui lòng kiểm tra thứ tự script');
            }
            this.live2dManager = new window.Live2DManager();
            await this.live2dManager.initializeLive2D();
            // 更新UI状态
            const live2dStatus = document.getElementById('live2dStatus');
            if (live2dStatus) {
                live2dStatus.textContent = '● Đã tải';
                live2dStatus.className = 'status loaded';
            }
            log('Khởi tạo Live2D hoàn tất', 'success');
        } catch (error) {
            log(`Khởi tạo Live2D thất bại: ${error.message}`, 'error');
            // 更新UI状态
            const live2dStatus = document.getElementById('live2dStatus');
            if (live2dStatus) {
                live2dStatus.textContent = '● Tải thất bại';
                live2dStatus.className = 'status error';
            }
        }
    }

    // 设置model加载状态
    setModelLoadingStatus(isLoading) {
        const modelLoading = document.getElementById('modelLoading');
        if (modelLoading) {
            modelLoading.style.display = isLoading ? 'flex' : 'none';
        }
    }

    /**
     * 检查麦克风可用性
     * 在应用初始化时调用，检查麦克风是否可用并更新UI状态
     */
    async checkMicrophoneAvailability() {
        try {
            const isAvailable = await checkMicrophoneAvailability();
            const isHttp = isHttpNonLocalhost();
            // 保存可用性状态到全局变量
            window.microphoneAvailable = isAvailable;
            window.isHttpNonLocalhost = isHttp;
            // 更新UI
            if (this.uiController) {
                this.uiController.updateMicrophoneAvailability(isAvailable, isHttp);
            }
            log(`Kiểm tra micro hoàn tất: ${isAvailable ? 'Khả dụng' : 'Không khả dụng'}`, isAvailable ? 'success' : 'warning');
        } catch (error) {
            log(`Kiểm tra micro thất bại: ${error.message}`, 'error');
            // 默认设置为不可用
            window.microphoneAvailable = false;
            window.isHttpNonLocalhost = isHttpNonLocalhost();
            if (this.uiController) {
                this.uiController.updateMicrophoneAvailability(false, window.isHttpNonLocalhost);
            }
        }
    }

    // 检查摄像头可用性
    checkCameraAvailability() {
        window.cameraAvailable = true;
        log('Kiểm tra camera hoàn tất: Mặc định đã liên kết', 'success');
    }

    // 初始化摄像头
    async initCamera() {
        const cameraContainer = document.getElementById('cameraContainer');
        const cameraVideo = document.getElementById('cameraVideo');
        const cameraSwitch = document.getElementById('cameraSwitch');
        const cameraSwitchMask = document.getElementById('cameraSwitchMask');
        const dialBtn = document.getElementById('dialBtn');

        if (!cameraContainer || !cameraVideo) {
            log('Không tìm thấy phần tử camera, bỏ qua khởi tạo', 'warning');
            return Promise.resolve(false);
        }

        let isDragging = false;
        let currentX, currentY, initialX, initialY;
        let xOffset = 0, yOffset = 0;

        cameraContainer.addEventListener('mousedown', dragStart);
        document.addEventListener('mousemove', drag);
        document.addEventListener('mouseup', dragEnd);
        cameraContainer.addEventListener('touchstart', dragStart, { passive: false });
        document.addEventListener('touchmove', drag, { passive: false });
        document.addEventListener('touchend', dragEnd);

        function dragStart(e) {
            if (e.type === 'touchstart') {
                initialX = e.touches[0].clientX - xOffset;
                initialY = e.touches[0].clientY - yOffset;
            } else {
                initialX = e.clientX - xOffset;
                initialY = e.clientY - yOffset;
            }
            isDragging = true;
            cameraContainer.classList.add('dragging');
        }

        function drag(e) {
            if (isDragging) {
                e.preventDefault();
                if (e.type === 'touchmove') {
                    currentX = e.touches[0].clientX - initialX;
                    currentY = e.touches[0].clientY - initialY;
                } else {
                    currentX = e.clientX - initialX;
                    currentY = e.clientY - initialY;
                }
                xOffset = currentX;
                yOffset = currentY;
                cameraContainer.style.transform = `translate3d(${currentX}px, ${currentY}px, 0)`;
            }
        }

        function dragEnd() {
            initialX = currentX;
            initialY = currentY;
            isDragging = false;
            cameraContainer.classList.remove('dragging');
        }

        return new Promise((resolve) => {
            window.startCamera = async () => {
                try {
                    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                        log('Trình duyệt không hỗ trợ Camera API', 'warning');
                        return false;
                    }
                    log('Đang yêu cầu quyền truy cập camera...', 'info');
                    this.cameraStream = await navigator.mediaDevices.getUserMedia({
                        video: { width: 320, height: 240, facingMode: this.currentFacingMode },
                        audio: false
                    });
                    cameraVideo.srcObject = this.cameraStream;
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    const videoDevices = devices.filter(device => device.kind === 'videoinput');
                    if (videoDevices.length > 1) {
                        if (cameraSwitch) cameraSwitch.classList.add('active'); 
                    }
                    cameraContainer.classList.add('active');

                    // 切换时挂断情况
                    const hasActive = dialBtn.classList.contains('dial-active');
                    if (!hasActive) {
                        cameraContainer.classList.remove('active');
                        cameraSwitch.classList.remove('active');
                        window.stopCamera();
                    }
                    log('Camera đã khởi động', 'success');
                    return true;
                } catch (error) {
                    log(`Khởi động camera thất bại: ${error.name} - ${error.message}`, 'error');
                    if (error.name === 'NotAllowedError') {
                        log('Quyền truy cập camera bị từ chối, vui lòng kiểm tra cài đặt trình duyệt', 'warning');
                    } else if (error.name === 'NotFoundError') {
                        log('Không tìm thấy thiết bị camera', 'warning');
                    } else if (error.name === 'NotReadableError') {
                        log('Camera đang bị ứng dụng khác sử dụng', 'warning');
                    }
                    return false;
                }
            };

            window.stopCamera = () => {
                if (this.cameraStream) {
                    this.cameraStream.getTracks().forEach(track => track.stop());
                    this.cameraStream = null;
                    cameraVideo.srcObject = null;
                    log('Camera đã đóng', 'info');
                }
            };

            window.switchCamera = async() => {
                if (window.switchCameraTimer) return;
                if (this.cameraStream) {
                    const currentTransform = window.getComputedStyle(cameraContainer).transform;
                    const originalTransform = currentTransform === 'none' ? 'translate(0px, 0px)' : currentTransform;
                    cameraContainer.style.setProperty('--original-transform', originalTransform);
                    cameraContainer.classList.add('flip');
                    if (cameraSwitchMask) cameraSwitchMask.style.opacity = 0; 
                    this.currentFacingMode = this.currentFacingMode === 'user' ? 'environment' : 'user';
                    window.stopCamera();
                    window.startCamera();
                    
                    window.switchCameraTimer = setTimeout(() => {
                        if (this.currentFacingMode === 'user') {
                            cameraVideo.style.transform = 'scaleX(-1)';
                        } else {
                            cameraVideo.style.transform = 'scaleX(1)';
                        }
                        window.switchCameraTimer = null;
                        cameraContainer.classList.remove('flip');
                        cameraContainer.style.removeProperty('--original-transform');
                        if (cameraSwitchMask) cameraSwitchMask.style.opacity = 1; 
                    }, 500);
                }
            };

            window.takePhoto = (question = 'Mô tả những gì bạn thấy') => {
                return new Promise(async (resolve) => {
                    const canvas = document.createElement('canvas');
                    const video = cameraVideo;

                    if (!video || video.readyState !== video.HAVE_ENOUGH_DATA) {
                        log('Không thể chụp ảnh: Camera chưa sẵn sàng', 'warning');
                        resolve({
                            success: false,
                            error: 'Camera chưa sẵn sàng, vui lòng đảm bảo đã kết nối và camera đã bật'
                        });
                        return;
                    }

                    canvas.width = video.videoWidth || 320;
                    canvas.height = video.videoHeight || 240;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                    const photoData = canvas.toDataURL('image/jpeg', 0.8);
                    log(`Chụp ảnh thành công, độ dài dữ liệu: ${photoData.length}`, 'success');

                    try {
                        const xz_tester_vision = localStorage.getItem('xz_tester_vision');
                        if (xz_tester_vision) {
                            let visionInfo = null;

                            try {
                                visionInfo = JSON.parse(xz_tester_vision);
                            } catch (err) {
                                throw new Error(`Phân tích cấu hình thị giác thất bại`);
                            }

                            const { url, token } = visionInfo || {};
                            if (!url || !token) {
                                throw new Error('Phân tích thị giác thất bại: Cấu hình thiếu địa chỉ (url) hoặc token');
                            }

                            log(`Đang gửi ảnh đến giao diện phân tích thị giác: ${url}`, 'info');

                            const deviceId = document.getElementById('deviceMac')?.value || '';
                            const clientId = document.getElementById('clientId')?.value || 'web_test_client';

                            const formData = new FormData();
                            formData.append('question', question);
                            formData.append('image', dataURItoBlob(photoData), 'photo.jpg');

                            const response = await fetch(url, {
                                method: 'POST',
                                body: formData,
                                headers: {
                                    'Device-Id': deviceId,
                                    'Client-Id': clientId,
                                    'Authorization': `Bearer ${token}`
                                }
                            });

                            if (!response.ok) {
                                throw new Error(`Lỗi HTTP! Trạng thái: ${response.status}`);
                            }

                            const analysisResult = await response.json();
                            log(`Phân tích thị giác hoàn tất: ${JSON.stringify(analysisResult).substring(0, 200)}...`, 'success');

                            resolve({
                                success: true,
                                message: question,
                                photo_data: photoData,
                                photo_width: canvas.width,
                                photo_height: canvas.height,
                                vision_analysis: analysisResult
                            });
                        } else {
                            log('Chưa cấu hình dịch vụ phân tích thị giác', 'warning');
                        }
                    } catch (error) {
                        log(`Phân tích thị giác thất bại: ${error.message}`, 'error');
                        resolve({
                            success: true,
                            message: question,
                            photo_data: photoData,
                            photo_width: canvas.width,
                            photo_height: canvas.height,
                            vision_analysis: {
                                success: false,
                                error: error.message,
                                fallback: 'Không thể kết nối dịch vụ phân tích thị giác'
                            }
                        });
                    }
                });
            };

            log('Khởi tạo camera hoàn tất', 'success');
            resolve(true);
        });
    }
}

// 创建并启动应用
const app = new App();
// 将应用实例暴露到全局，供其他模块访问
window.chatApp = app;
document.addEventListener('DOMContentLoaded', () => {
    // 初始化应用
    app.init();
});
export default app;
