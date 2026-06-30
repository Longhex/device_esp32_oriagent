package xiaozhi.modules.model.service.impl;

import java.io.Serializable;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.incrementer.DefaultIdentifierGenerator;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.core.metadata.OrderItem;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import cn.hutool.core.collection.CollectionUtil;
import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONObject;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.common.utils.ConvertUtils;
import xiaozhi.common.utils.SensitiveDataUtils;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.model.dao.ModelConfigDao;
import xiaozhi.modules.model.dto.LlmModelBasicInfoDTO;
import xiaozhi.modules.model.dto.ModelBasicInfoDTO;
import xiaozhi.modules.model.dto.ModelConfigBodyDTO;
import xiaozhi.modules.model.dto.ModelConfigDTO;
import xiaozhi.modules.model.dto.ModelProviderDTO;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.model.service.ModelProviderService;
import xiaozhi.modules.timbre.dao.TimbreDao;
import xiaozhi.modules.timbre.entity.TimbreEntity;

@Service
@AllArgsConstructor
public class ModelConfigServiceImpl extends BaseServiceImpl<ModelConfigDao, ModelConfigEntity>
        implements ModelConfigService {

    private final ModelConfigDao modelConfigDao;
    private final ModelProviderService modelProviderService;
    private final RedisUtils redisUtils;
    private final AgentDao agentDao;
    private final TimbreDao timbreDao;

    /** Provider code của Voice Oriagent (đa giọng — mỗi API key một giọng). */
    private static final String ORIAGENT_VOICE_TYPE = "oriagent_voice";

    @Override
    public List<ModelBasicInfoDTO> getModelCodeList(String modelType, String modelName) {
        List<ModelConfigEntity> entities = modelConfigDao.selectList(
                new QueryWrapper<ModelConfigEntity>()
                        .eq("model_type", modelType)
                        .eq("is_enabled", 1)
                        .like(StringUtils.isNotBlank(modelName), "model_name", modelName)
                        .select("id", "model_name")
                        .orderByAsc("sort"));
        return ConvertUtils.sourceToTarget(entities, ModelBasicInfoDTO.class);
    }

    @Override
    public List<LlmModelBasicInfoDTO> getLlmModelCodeList(String modelName) {
        List<ModelConfigEntity> entities = modelConfigDao.selectList(
                new QueryWrapper<ModelConfigEntity>()
                        .eq("model_type", "llm")
                        .eq("is_enabled", 1)
                        .like(StringUtils.isNotBlank(modelName), "model_name", modelName)
                        .select("id", "model_name", "config_json"));

        return entities.stream().map(item -> {
            LlmModelBasicInfoDTO dto = new LlmModelBasicInfoDTO();
            dto.setId(item.getId());
            dto.setModelName(item.getModelName());
            String type = item.getConfigJson().getOrDefault("type", "").toString();
            dto.setType(type);
            return dto;
        }).toList();
    }

    @Override
    public PageData<ModelConfigDTO> getPageList(String modelType, String modelName, String page, String limit) {
        Map<String, Object> params = new HashMap<>();
        params.put(Constant.PAGE, page);
        params.put(Constant.LIMIT, limit);

        long curPage = Long.parseLong(page);
        long pageSize = Long.parseLong(limit);
        Page<ModelConfigEntity> pageInfo = new Page<>(curPage, pageSize);

        // 添加排序规则：先按is_enabled降序，再按sort升序
        pageInfo.addOrder(OrderItem.desc("is_enabled"), OrderItem.asc("sort"));

        IPage<ModelConfigEntity> modelConfigEntityIPage = modelConfigDao.selectPage(
                pageInfo,
                new QueryWrapper<ModelConfigEntity>()
                        .eq("model_type", modelType)
                        .like(StringUtils.isNotBlank(modelName), "model_name", modelName));

        return getPageData(modelConfigEntityIPage, ModelConfigDTO.class);
    }

    @Override
    public ModelConfigDTO edit(String modelType, String provideCode, String id, ModelConfigBodyDTO modelConfigBodyDTO) {
        // 1. 参数验证
        validateEditParameters(modelType, provideCode, id, modelConfigBodyDTO);

        // 2. 验证模型提供者
        validateModelProvider(modelType, provideCode);

        // 3. 获取原始配置（不经过敏感数据处理）
        ModelConfigEntity originalEntity = getOriginalConfigFromDb(id);

        // 4. 验证LLM配置
        validateLlmConfiguration(modelConfigBodyDTO);

        // 5. 准备更新实体并处理敏感数据
        ModelConfigEntity modelConfigEntity = prepareUpdateEntity(modelConfigBodyDTO, originalEntity, modelType, id);

        // 6. 执行数据库更新
        modelConfigDao.updateById(modelConfigEntity);

        // 6.1 Voice Oriagent: đồng bộ lại danh sách giọng -> bảng ai_tts_voice.
        syncOriagentVoices(id, provideCode, modelConfigEntity.getConfigJson());

        // 7. 清除缓存
        clearModelCache(id);

        // 8. 返回处理后的数据（包含敏感数据掩码）
        return buildResponseDTO(modelConfigEntity);
    }

    @Override
    public ModelConfigDTO add(String modelType, String provideCode, ModelConfigBodyDTO modelConfigBodyDTO) {
        validateAddParameters(modelType, provideCode, modelConfigBodyDTO);

        validateModelProvider(modelType, provideCode);

        ModelConfigEntity modelConfigEntity = prepareAddEntity(modelConfigBodyDTO, modelType);

        modelConfigDao.insert(modelConfigEntity);

        // Voice Oriagent: tự đồng bộ danh sách giọng -> bảng ai_tts_voice (api_key giữ trong config).
        syncOriagentVoices(modelConfigEntity.getId(), provideCode, modelConfigEntity.getConfigJson());

        return buildResponseDTO(modelConfigEntity);
    }

    @Override
    public void delete(String id) {
        if (StringUtils.isBlank(id)) {
            throw new RenException(ErrorCode.IDENTIFIER_NOT_NULL);
        }

        ModelConfigEntity modelConfig = modelConfigDao.selectById(id);
        if (modelConfig != null && modelConfig.getIsDefault() == 1) {
            throw new RenException(ErrorCode.DEFAULT_MODEL_DELETE_ERROR);
        }

        checkAgentReference(id);
        checkIntentConfigReference(id);

        modelConfigDao.deleteById(id);

        // Voice Oriagent: xóa kèm các giọng đã auto-sync trong ai_tts_voice.
        if (modelConfig != null && isOriagentVoiceConfig(modelConfig.getConfigJson())) {
            timbreDao.delete(new QueryWrapper<TimbreEntity>().eq("tts_model_id", id));
        }

        clearModelCache(id);
    }

    @Override
    public String getModelNameById(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }

        String cacheKey = RedisKeys.getModelNameById(id);
        String cachedName = (String) redisUtils.get(cacheKey);
        if (StringUtils.isNotBlank(cachedName)) {
            return cachedName;
        }

        ModelConfigEntity entity = modelConfigDao.selectById(id);
        if (entity != null) {
            String modelName = entity.getModelName();
            if (StringUtils.isNotBlank(modelName)) {
                redisUtils.set(cacheKey, modelName);
            }
            return modelName;
        }

        return null;
    }

    @Override
    public ModelConfigEntity selectById(Serializable id) {
        return selectById(id, true);
    }

    @Override
    public ModelConfigEntity selectById(Serializable id, boolean mask) {
        ModelConfigEntity entity = super.selectById(id);
        if (entity != null && entity.getConfigJson() != null && mask) {
            entity.setConfigJson(maskSensitiveFields(entity.getConfigJson()));
        }
        return entity;
    }

    @Override
    protected <D> PageData<D> getPageData(IPage<?> page, Class<D> target) {
        List<?> records = page.getRecords();
        if (records != null && !records.isEmpty()) {
            for (Object record : records) {
                if (record instanceof ModelConfigEntity) {
                    ModelConfigEntity entity = (ModelConfigEntity) record;
                    if (entity.getConfigJson() != null) {
                        entity.setConfigJson(maskSensitiveFields(entity.getConfigJson()));
                    }
                }
            }
        }
        return super.getPageData(page, target);
    }

    @Override
    public ModelConfigEntity getModelByIdFromCache(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }
        String cacheKey = RedisKeys.getModelConfigById(id);
        ModelConfigEntity entity = (ModelConfigEntity) redisUtils.get(cacheKey);
        if (entity == null) {
            entity = modelConfigDao.selectById(id);
            if (entity != null) {
                redisUtils.set(cacheKey, entity);
            }
        }
        return entity;
    }

    /**
     * 验证编辑参数
     */
    private void validateEditParameters(String modelType, String provideCode, String id,
            ModelConfigBodyDTO modelConfigBodyDTO) {
        if (StringUtils.isBlank(modelType) || StringUtils.isBlank(provideCode)) {
            throw new RenException(ErrorCode.MODEL_TYPE_PROVIDE_CODE_NOT_NULL);
        }
        if (StringUtils.isBlank(id)) {
            throw new RenException(ErrorCode.IDENTIFIER_NOT_NULL);
        }
        if (modelConfigBodyDTO == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
    }

    /**
     * 验证添加参数
     */
    private void validateAddParameters(String modelType, String provideCode, ModelConfigBodyDTO modelConfigBodyDTO) {
        if (StringUtils.isBlank(modelType) || StringUtils.isBlank(provideCode)) {
            throw new RenException(ErrorCode.MODEL_TYPE_PROVIDE_CODE_NOT_NULL);
        }
        if (modelConfigBodyDTO == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        if (StringUtils.isBlank(modelConfigBodyDTO.getId())) {
            // 参照 MP @TableId AutoUUID 策略使用
            // com.baomidou.mybatisplus.core.incrementer.DefaultIdentifierGenerator(UUID.replace("-",""))
            // 进行分配默认模型ID
            modelConfigBodyDTO.setId(DefaultIdentifierGenerator.getInstance().nextUUID(ModelConfigEntity.class));
        }
    }

    /**
     * 设置默认模型
     */
    @Override
    public void setDefaultModel(String modelType, int isDefault) {
        // 参数验证
        if (StringUtils.isBlank(modelType)) {
            throw new RenException(ErrorCode.MODEL_TYPE_PROVIDE_CODE_NOT_NULL);
        }

        ModelConfigEntity entity = new ModelConfigEntity();
        entity.setIsDefault(isDefault);
        modelConfigDao.update(entity, new QueryWrapper<ModelConfigEntity>()
                .eq("model_type", modelType));

        // 清除相关缓存
        clearModelCacheByType(modelType);
    }

    /**
     * 验证模型提供者
     */
    private void validateModelProvider(String modelType, String provideCode) {
        List<ModelProviderDTO> providerList = modelProviderService.getList(modelType, provideCode);
        if (CollectionUtil.isEmpty(providerList)) {
            throw new RenException(ErrorCode.MODEL_PROVIDER_NOT_EXIST);
        }
    }

    /**
     * 从数据库获取原始配置（不经过敏感数据处理）
     */
    private ModelConfigEntity getOriginalConfigFromDb(String id) {
        ModelConfigEntity originalEntity = modelConfigDao.selectById(id);
        if (originalEntity == null) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        return originalEntity;
    }

    /**
     * 验证LLM配置
     */
    private void validateLlmConfiguration(ModelConfigBodyDTO modelConfigBodyDTO) {
        if (modelConfigBodyDTO.getConfigJson() != null && modelConfigBodyDTO.getConfigJson().containsKey("llm")) {
            String llm = modelConfigBodyDTO.getConfigJson().get("llm").toString();
            ModelConfigEntity modelConfigEntity = modelConfigDao.selectOne(new LambdaQueryWrapper<ModelConfigEntity>()
                    .eq(ModelConfigEntity::getId, llm));

            if (modelConfigEntity == null) {
                throw new RenException(ErrorCode.LLM_NOT_EXIST);
            }

            String modelType = modelConfigEntity.getModelType();
            if (modelType == null || !"LLM".equals(modelType.toUpperCase())) {
                throw new RenException(ErrorCode.LLM_NOT_EXIST);
            }

            // 验证LLM类型
            JSONObject configJson = modelConfigEntity.getConfigJson();
            if (configJson != null && configJson.containsKey("type")) {
                String type = configJson.get("type").toString();
                if (!"openai".equals(type) && !"ollama".equals(type)) {
                    throw new RenException(ErrorCode.INVALID_LLM_TYPE);
                }
            }
        }
    }

    /**
     * 准备更新实体，处理敏感数据
     */
    private ModelConfigEntity prepareUpdateEntity(ModelConfigBodyDTO modelConfigBodyDTO,
            ModelConfigEntity originalEntity,
            String modelType,
            String id) {
        // 1. 复制原始实体，保留所有原始数据（包括敏感信息）
        ModelConfigEntity modelConfigEntity = ConvertUtils.sourceToTarget(originalEntity, ModelConfigEntity.class);
        modelConfigEntity.setId(id);
        modelConfigEntity.setModelType(modelType);

        // 2. 只更新非敏感字段
        modelConfigEntity.setModelName(modelConfigBodyDTO.getModelName());
        modelConfigEntity.setSort(modelConfigBodyDTO.getSort());
        modelConfigEntity.setIsEnabled(modelConfigBodyDTO.getIsEnabled());
        modelConfigEntity.setRemark(modelConfigBodyDTO.getRemark());
        // 3. 处理配置JSON，仅更新非敏感字段和明确修改的敏感字段
        if (modelConfigBodyDTO.getConfigJson() != null && originalEntity.getConfigJson() != null) {
            JSONObject originalJson = originalEntity.getConfigJson();
            JSONObject updatedJson = new JSONObject(originalJson); // 基于原始JSON进行修改

            // 遍历更新的JSON，只更新非敏感字段或确实被修改的敏感字段
            for (String key : modelConfigBodyDTO.getConfigJson().keySet()) {
                Object value = modelConfigBodyDTO.getConfigJson().get(key);

                // 如果是敏感字段，需要确认是否真的被修改（前端传入的可能是掩码后的值）
                if (SensitiveDataUtils.isSensitiveField(key)) {

                    if (value instanceof String && !SensitiveDataUtils.isMaskedValue((String) value)) {
                        updatedJson.put(key, value);
                    }
                } else if ("voices".equals(key) && value instanceof JSONArray) {
                    // Voice Oriagent: merge mảng giọng, giữ api_key gốc khi giá trị gửi lên là mask.
                    updatedJson.set("voices",
                            mergeVoices(originalJson.getJSONArray("voices"), (JSONArray) value));
                } else if (value instanceof JSONObject) {
                    // 递归处理嵌套JSON
                    mergeJson(updatedJson, key, (JSONObject) value);
                } else {
                    // 非敏感字段直接更新
                    updatedJson.put(key, value);
                }
            }

            modelConfigEntity.setConfigJson(updatedJson);
        }

        return modelConfigEntity;
    }

    // 辅助方法：判断值是否是掩码格式
    private boolean isMaskedValue(String value) {
        if (value == null)
            return false;
        // 简单判断是否包含掩码的特征（***）
        return value.contains("***");
    }

    // 辅助方法：递归合并JSON，保留原始敏感字段
    private void mergeJson(JSONObject original, String key, JSONObject updated) {
        if (!original.containsKey(key)) {
            original.put(key, new JSONObject());
        }
        JSONObject originalChild = original.getJSONObject(key);

        for (String childKey : updated.keySet()) {
            Object childValue = updated.get(childKey);
            if (childValue instanceof JSONObject) {
                mergeJson(originalChild, childKey, (JSONObject) childValue);
            } else {
                if (!SensitiveDataUtils.isSensitiveField(childKey) ||
                        (childValue instanceof String && !isMaskedValue((String) childValue))) {
                    originalChild.put(childKey, childValue);
                }
            }
        }
    }

    /**
     * 准备新增实体
     */
    private ModelConfigEntity prepareAddEntity(ModelConfigBodyDTO modelConfigBodyDTO, String modelType) {
        ModelConfigEntity modelConfigEntity = ConvertUtils.sourceToTarget(modelConfigBodyDTO, ModelConfigEntity.class);
        modelConfigEntity.setModelType(modelType);
        modelConfigEntity.setIsDefault(0);
        return modelConfigEntity;
    }

    /** Kiểm tra config có phải Voice Oriagent (đa giọng) không. */
    private boolean isOriagentVoiceConfig(JSONObject configJson) {
        return configJson != null && ORIAGENT_VOICE_TYPE.equals(configJson.getStr("type"));
    }

    /**
     * Merge mảng voices khi cập nhật: nếu api_key gửi lên là giá trị mask (****),
     * khôi phục api_key gốc theo tên giọng để không ghi đè key thật bằng mask.
     */
    private JSONArray mergeVoices(JSONArray original, JSONArray incoming) {
        Map<String, String> originalKeyByName = new HashMap<>();
        if (original != null) {
            for (Object o : original) {
                if (o instanceof JSONObject) {
                    JSONObject v = (JSONObject) o;
                    originalKeyByName.put(v.getStr("name"), v.getStr("api_key"));
                }
            }
        }
        JSONArray result = new JSONArray();
        if (incoming != null) {
            for (Object o : incoming) {
                if (o instanceof JSONObject) {
                    JSONObject v = new JSONObject((JSONObject) o);
                    String apiKey = v.getStr("api_key");
                    if (apiKey != null && SensitiveDataUtils.isMaskedValue(apiKey)) {
                        String orig = originalKeyByName.get(v.getStr("name"));
                        if (StringUtils.isNotBlank(orig)) {
                            v.set("api_key", orig);
                        }
                    }
                    result.add(v);
                } else {
                    result.add(o);
                }
            }
        }
        return result;
    }

    /**
     * Đồng bộ danh sách giọng của model Voice Oriagent vào bảng ai_tts_voice.
     * - Mỗi giọng -> 1 bản ghi (name = tts_voice = tên giọng, languages = ngôn ngữ).
     * - api_key KHÔNG lưu ở đây (chỉ nằm trong config model, đã mask khi đọc).
     * - Match theo tên để giữ nguyên id (agent đang tham chiếu không bị vỡ); xóa giọng đã bỏ.
     */
    private void syncOriagentVoices(String modelId, String provideCode, JSONObject configJson) {
        boolean isOriagent = ORIAGENT_VOICE_TYPE.equals(provideCode) || isOriagentVoiceConfig(configJson);
        if (!isOriagent || StringUtils.isBlank(modelId)) {
            return;
        }
        JSONArray voices = configJson == null ? null : configJson.getJSONArray("voices");

        List<TimbreEntity> existing = timbreDao.selectList(
                new QueryWrapper<TimbreEntity>().eq("tts_model_id", modelId));
        Map<String, TimbreEntity> byName = new HashMap<>();
        for (TimbreEntity e : existing) {
            byName.put(e.getName(), e);
        }

        Set<String> keepNames = new HashSet<>();
        long sort = 1;
        if (voices != null) {
            for (Object o : voices) {
                if (!(o instanceof JSONObject)) {
                    continue;
                }
                JSONObject v = (JSONObject) o;
                String name = v.getStr("name");
                if (StringUtils.isBlank(name)) {
                    continue;
                }
                String language = StringUtils.defaultIfBlank(v.getStr("language"), "auto");
                keepNames.add(name);
                TimbreEntity row = byName.get(name);
                if (row == null) {
                    row = new TimbreEntity();
                    row.setId(DefaultIdentifierGenerator.getInstance().nextUUID(TimbreEntity.class));
                    row.setTtsModelId(modelId);
                    row.setName(name);
                    row.setTtsVoice(name);
                    row.setLanguages(language);
                    row.setSort(sort);
                    timbreDao.insert(row);
                } else {
                    row.setTtsVoice(name);
                    row.setLanguages(language);
                    row.setSort(sort);
                    timbreDao.updateById(row);
                    redisUtils.delete(RedisKeys.getTimbreDetailsKey(row.getId()));
                    redisUtils.delete(RedisKeys.getTimbreNameById(row.getId()));
                }
                sort++;
            }
        }

        for (TimbreEntity e : existing) {
            if (!keepNames.contains(e.getName())) {
                timbreDao.deleteById(e.getId());
                redisUtils.delete(RedisKeys.getTimbreDetailsKey(e.getId()));
                redisUtils.delete(RedisKeys.getTimbreNameById(e.getId()));
            }
        }
    }

    /**
     * 构建返回的DTO，处理敏感数据
     */
    private ModelConfigDTO buildResponseDTO(ModelConfigEntity entity) {
        ModelConfigDTO dto = ConvertUtils.sourceToTarget(entity, ModelConfigDTO.class);
        if (dto.getConfigJson() != null) {
            dto.setConfigJson(maskSensitiveFields(dto.getConfigJson()));
        }
        return dto;
    }

    /**
     * 处理敏感字段
     */
    private JSONObject maskSensitiveFields(JSONObject configJson) {
        return SensitiveDataUtils.maskSensitiveFields(configJson);
    }

    /**
     * 清除模型缓存
     */
    private void clearModelCache(String id) {
        redisUtils.delete(RedisKeys.getModelConfigById(id));
        redisUtils.delete(RedisKeys.getModelNameById(id));
    }

    /**
     * 按模型类型清除缓存
     */
    private void clearModelCacheByType(String modelType) {
        List<ModelConfigEntity> entities = modelConfigDao.selectList(
                new QueryWrapper<ModelConfigEntity>().eq("model_type", modelType));
        for (ModelConfigEntity entity : entities) {
            clearModelCache(entity.getId());
        }
    }

    /**
     * 检查智能体配置是否有引用
     */
    private void checkAgentReference(String modelId) {
        List<AgentEntity> agents = agentDao.selectList(
                new QueryWrapper<AgentEntity>()
                        .eq("vad_model_id", modelId)
                        .or()
                        .eq("asr_model_id", modelId)
                        .or()
                        .eq("llm_model_id", modelId)
                        .or()
                        .eq("tts_model_id", modelId)
                        .or()
                        .eq("mem_model_id", modelId)
                        .or()
                        .eq("vllm_model_id", modelId)
                        .or()
                        .eq("intent_model_id", modelId));
        if (!agents.isEmpty()) {
            String agentNames = agents.stream()
                    .map(AgentEntity::getAgentName)
                    .collect(Collectors.joining("、"));
            throw new RenException(ErrorCode.MODEL_REFERENCED_BY_AGENT, agentNames);
        }
    }

    /**
     * 检查意图识别配置是否有引用
     */
    private void checkIntentConfigReference(String modelId) {
        ModelConfigEntity modelConfig = modelConfigDao.selectById(modelId);
        if (modelConfig != null
                && "LLM".equals(modelConfig.getModelType() == null ? null : modelConfig.getModelType().toUpperCase())) {
            List<ModelConfigEntity> intentConfigs = modelConfigDao.selectList(
                    new QueryWrapper<ModelConfigEntity>()
                            .eq("model_type", "Intent")
                            .like("config_json", modelId));
            if (!intentConfigs.isEmpty()) {
                throw new RenException(ErrorCode.LLM_REFERENCED_BY_INTENT);
            }
        }
    }

    /**
     * 获取符合条件的TTS平台列表
     */
    @Override
    public List<Map<String, Object>> getTtsPlatformList() {
        return modelConfigDao.getTtsPlatformList();
    }

    /**
     * 根据模型类型获取所有启用的模型配置
     */
    @Override
    public List<ModelConfigEntity> getEnabledModelsByType(String modelType) {
        if (StringUtils.isBlank(modelType)) {
            return null;
        }

        List<ModelConfigEntity> entities = modelConfigDao.selectList(
                new QueryWrapper<ModelConfigEntity>()
                        .eq("model_type", modelType)
                        .eq("is_enabled", 1)
                        .orderByAsc("sort"));

        return entities;
    }
}
