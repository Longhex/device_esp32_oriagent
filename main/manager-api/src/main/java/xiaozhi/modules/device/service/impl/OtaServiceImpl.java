package xiaozhi.modules.device.service.impl;

import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import io.micrometer.common.util.StringUtils;
import xiaozhi.common.page.PageData;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.modules.device.dao.OtaDao;
import xiaozhi.modules.device.entity.OtaEntity;
import xiaozhi.modules.device.service.OtaService;

@Service
public class OtaServiceImpl extends BaseServiceImpl<OtaDao, OtaEntity> implements OtaService {

    @Override
    public PageData<OtaEntity> page(Map<String, Object> params) {
        IPage<OtaEntity> page = baseDao.selectPage(
                getPage(params, "update_date", true),
                getWrapper(params));

        return new PageData<>(page.getRecords(), page.getTotal());
    }

    private QueryWrapper<OtaEntity> getWrapper(Map<String, Object> params) {
        String firmwareName = (String) params.get("firmwareName");
        String type = (String) params.get("type");
        String excludeType = (String) params.get("excludeType");
        String typePrefix = (String) params.get("typePrefix");
        String excludeTypePrefix = (String) params.get("excludeTypePrefix");

        QueryWrapper<OtaEntity> wrapper = new QueryWrapper<>();
        wrapper.like(StringUtils.isNotBlank(firmwareName), "firmware_name", firmwareName);
        // 精确按类型筛选
        wrapper.eq(StringUtils.isNotBlank(type), "type", type);
        wrapper.ne(StringUtils.isNotBlank(excludeType), "type", excludeType);
        // 按类型前缀筛选（资源页传 typePrefix=asset- 列出全部资源；每种资源 type=asset-<key>）
        wrapper.likeRight(StringUtils.isNotBlank(typePrefix), "type", typePrefix);
        // 排除类型前缀（固件页传 excludeTypePrefix=asset- 隐藏所有资源文件）
        wrapper.apply(StringUtils.isNotBlank(excludeTypePrefix), "type NOT LIKE {0}",
                StringUtils.isNotBlank(excludeTypePrefix) ? excludeTypePrefix + "%" : "");

        return wrapper;
    }

    @Override
    public void update(OtaEntity entity) {
        // 检查是否存在相同类型和版本的固件（排除当前记录）
        QueryWrapper<OtaEntity> queryWrapper = new QueryWrapper<OtaEntity>()
                .eq("type", entity.getType())
                .eq("version", entity.getVersion())
                .ne("id", entity.getId()); // 排除当前记录

        if (baseDao.selectCount(queryWrapper) > 0) {
            throw new RuntimeException("Đã tồn tại firmware cùng loại và phiên bản, vui lòng sửa rồi thử lại");
        }

        entity.setUpdateDate(new Date());
        baseDao.updateById(entity);
    }

    @Override
    public void delete(String[] ids) {
        baseDao.deleteBatchIds(Arrays.asList(ids));
    }

    @Override
    public boolean save(OtaEntity entity) {
        QueryWrapper<OtaEntity> queryWrapper = new QueryWrapper<OtaEntity>()
                .eq("type", entity.getType());
        // 同类固件只保留最新的一条
        List<OtaEntity> otaList = baseDao.selectList(queryWrapper);
        if (otaList != null && otaList.size() > 0) {
            OtaEntity otaBefore = otaList.get(0);
            entity.setId(otaBefore.getId());
            baseDao.updateById(entity);
            return true;
        }
        return baseDao.insert(entity) > 0;
    }

    @Override
    public OtaEntity getLatestOta(String type) {
        QueryWrapper<OtaEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("type", type)
                .orderByDesc("update_date")
                .last("LIMIT 1");
        return baseDao.selectOne(wrapper);
    }

    @Override
    public List<OtaEntity> listByTypePrefix(String typePrefix) {
        QueryWrapper<OtaEntity> wrapper = new QueryWrapper<>();
        wrapper.likeRight("type", typePrefix)
                .orderByAsc("type");
        return baseDao.selectList(wrapper);
    }
}