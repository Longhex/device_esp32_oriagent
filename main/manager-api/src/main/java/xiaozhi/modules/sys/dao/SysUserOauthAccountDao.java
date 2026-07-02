package xiaozhi.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;
import xiaozhi.common.dao.BaseDao;
import xiaozhi.modules.sys.entity.SysUserOauthAccountEntity;

/**
 * OAuth Account mapping
 */
@Mapper
public interface SysUserOauthAccountDao extends BaseDao<SysUserOauthAccountEntity> {

}
