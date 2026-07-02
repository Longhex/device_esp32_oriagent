package xiaozhi.common.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "oauth.google")
public class GoogleOAuthProperties {
    private boolean enabled;
    private String clientId;
    private String clientSecret;
    private String scope = "openid email profile";
    private String authUri = "https://accounts.google.com/o/oauth2/v2/auth";
    private String tokenUri = "https://oauth2.googleapis.com/token";
    private String userInfoUri = "https://openidconnect.googleapis.com/v1/userinfo";
}
