package xiaozhi.modules.sys.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.entity.BaseEntity;

/**
 * OAuth Account mapping
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_user_oauth_account")
public class SysUserOauthAccountEntity extends BaseEntity {
    /**
     * User ID
     */
    private Long userId;
    /**
     * Provider (e.g. google)
     */
    private String provider;
    /**
     * Provider Account ID (e.g. Google Sub)
     */
    private String providerAccountId;
    /**
     * Email from provider
     */
    private String email;
}
