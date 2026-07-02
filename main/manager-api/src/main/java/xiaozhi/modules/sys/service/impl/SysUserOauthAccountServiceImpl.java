package xiaozhi.modules.sys.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import lombok.AllArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.modules.sys.dao.SysUserOauthAccountDao;
import xiaozhi.modules.sys.entity.SysUserOauthAccountEntity;
import xiaozhi.modules.sys.service.SysUserOauthAccountService;

@AllArgsConstructor
@Service
public class SysUserOauthAccountServiceImpl extends BaseServiceImpl<SysUserOauthAccountDao, SysUserOauthAccountEntity> implements SysUserOauthAccountService {

    @Override
    public SysUserOauthAccountEntity getByProviderAndAccountId(String provider, String providerAccountId) {
        QueryWrapper<SysUserOauthAccountEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("provider", provider);
        queryWrapper.eq("provider_account_id", providerAccountId);
        return baseDao.selectOne(queryWrapper);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void bindAccount(Long userId, String provider, String providerAccountId, String email) {
        SysUserOauthAccountEntity account = getByProviderAndAccountId(provider, providerAccountId);
        if (account == null) {
            account = new SysUserOauthAccountEntity();
            account.setUserId(userId);
            account.setProvider(provider);
            account.setProviderAccountId(providerAccountId);
            account.setEmail(email);
            baseDao.insert(account);
        } else {
            // Update email if necessary
            if (email != null && !email.equals(account.getEmail())) {
                account.setEmail(email);
                baseDao.updateById(account);
            }
        }
    }
}
