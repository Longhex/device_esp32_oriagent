package xiaozhi.modules.device.service;

import java.util.List;
import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.device.entity.OtaEntity;

/**
 * OTA固件管理
 */
public interface OtaService extends BaseService<OtaEntity> {
    PageData<OtaEntity> page(Map<String, Object> params);

    boolean save(OtaEntity entity);

    void update(OtaEntity entity);

    void delete(String[] ids);

    OtaEntity getLatestOta(String type);

    /**
     * 按类型前缀列出全部资源（如 asset-），用于设备一次性拉取所有资源版本与下载链接
     */
    List<OtaEntity> listByTypePrefix(String typePrefix);
}