package xiaozhi.modules.sys.service;

import xiaozhi.common.service.BaseService;
import xiaozhi.modules.sys.entity.SysUserOauthAccountEntity;

/**
 * OAuth Account mapping
 */
public interface SysUserOauthAccountService extends BaseService<SysUserOauthAccountEntity> {

    SysUserOauthAccountEntity getByProviderAndAccountId(String provider, String providerAccountId);

    void bindAccount(Long userId, String provider, String providerAccountId, String email);
}
