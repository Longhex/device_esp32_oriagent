package xiaozhi.modules.security.controller;

import cn.hutool.core.util.IdUtil;
import cn.hutool.http.HttpUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.StringUtils;
import org.springframework.web.bind.annotation.*;
import xiaozhi.common.config.GoogleOAuthProperties;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.TokenDTO;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.dto.SysUserDTO;
import xiaozhi.modules.sys.entity.SysUserOauthAccountEntity;
import xiaozhi.modules.sys.service.SysUserOauthAccountService;
import xiaozhi.modules.sys.service.SysUserService;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@AllArgsConstructor
@RestController
@RequestMapping("/user/google")
@Tag(name = "Google OAuth 登录")
public class GoogleOAuthController {

    private final GoogleOAuthProperties googleOAuthProperties;
    private final SysUserService sysUserService;
    private final SysUserOauthAccountService sysUserOauthAccountService;
    private final SysUserTokenService sysUserTokenService;
    private final RedisUtils redisUtils;

    private static final String STATE_CACHE_PREFIX = "oauth:google:state:";
    private static final long STATE_EXPIRE = 60 * 5; // 5 minutes

    @GetMapping("/auth-url")
    @Operation(summary = "获取 Google 授权链接")
    public Result<Map<String, String>> getAuthUrl(@RequestParam String redirectUri) {
        if (!googleOAuthProperties.isEnabled()) {
            throw new RenException("Google OAuth is disabled");
        }

        String state = IdUtil.fastSimpleUUID();
        // Save state to Redis to verify later
        redisUtils.set(STATE_CACHE_PREFIX + state, redirectUri, STATE_EXPIRE);

        String url = String.format("%s?client_id=%s&redirect_uri=%s&response_type=code&scope=%s&state=%s",
                googleOAuthProperties.getAuthUri(),
                googleOAuthProperties.getClientId(),
                redirectUri,
                googleOAuthProperties.getScope(),
                state);

        Map<String, String> result = new HashMap<>();
        result.put("authUrl", url);
        return new Result<Map<String, String>>().ok(result);
    }

    @PostMapping("/callback")
    @Operation(summary = "Google 回调处理")
    public Result<TokenDTO> callback(@RequestBody Map<String, String> body) {
        if (!googleOAuthProperties.isEnabled()) {
            throw new RenException("Google OAuth is disabled");
        }

        String code = body.get("code");
        String state = body.get("state");
        String redirectUri = body.get("redirectUri");

        if (StringUtils.isBlank(code) || StringUtils.isBlank(state)) {
            throw new RenException("Invalid authorization code or state");
        }

        // Verify state
        String cachedRedirectUri = (String) redisUtils.get(STATE_CACHE_PREFIX + state);
        if (cachedRedirectUri == null) {
            throw new RenException("State expired or invalid");
        }
        redisUtils.delete(STATE_CACHE_PREFIX + state);

        // Request token
        Map<String, Object> tokenParams = new HashMap<>();
        tokenParams.put("client_id", googleOAuthProperties.getClientId());
        tokenParams.put("client_secret", googleOAuthProperties.getClientSecret());
        tokenParams.put("code", code);
        tokenParams.put("grant_type", "authorization_code");
        tokenParams.put("redirect_uri", redirectUri != null ? redirectUri : cachedRedirectUri);

        String tokenResponse;
        try {
            tokenResponse = HttpUtil.post(googleOAuthProperties.getTokenUri(), tokenParams);
        } catch (Exception e) {
            log.error("Failed to fetch Google token", e);
            throw new RenException("Failed to fetch Google token");
        }

        JSONObject tokenJson = JSONUtil.parseObj(tokenResponse);
        if (tokenJson.containsKey("error")) {
            log.error("Google token error: {}", tokenResponse);
            throw new RenException("Google token error: " + tokenJson.getStr("error_description"));
        }

        String accessToken = tokenJson.getStr("access_token");

        // Fetch User Info
        String userInfoResponse;
        try {
            userInfoResponse = HttpUtil.createGet(googleOAuthProperties.getUserInfoUri())
                    .header("Authorization", "Bearer " + accessToken)
                    .execute().body();
        } catch (Exception e) {
            log.error("Failed to fetch Google user info", e);
            throw new RenException("Failed to fetch Google user info");
        }

        JSONObject userInfoJson = JSONUtil.parseObj(userInfoResponse);
        if (userInfoJson.containsKey("error")) {
            log.error("Google user info error: {}", userInfoResponse);
            throw new RenException("Failed to fetch Google user info");
        }

        String googleId = userInfoJson.getStr("sub");
        String email = userInfoJson.getStr("email");

        if (StringUtils.isBlank(googleId) || StringUtils.isBlank(email)) {
            throw new RenException("Cannot retrieve valid Google account information");
        }

        SysUserOauthAccountEntity oauthAccount = sysUserOauthAccountService.getByProviderAndAccountId("google", googleId);
        Long userId;

        if (oauthAccount != null) {
            userId = oauthAccount.getUserId();
        } else {
            // Check if user already exists by email (used as username)
            SysUserDTO existingUser = sysUserService.getByUsername(email);
            if (existingUser != null) {
                userId = existingUser.getId();
            } else {
                // Register new user
                SysUserDTO newUser = new SysUserDTO();
                newUser.setUsername(email);
                // Assign a strong random password for Google-registered users
                newUser.setPassword(IdUtil.fastSimpleUUID() + "Aa1!");
                sysUserService.save(newUser);
                
                // Fetch the newly created user
                existingUser = sysUserService.getByUsername(email);
                userId = existingUser.getId();
            }
            // Bind account
            sysUserOauthAccountService.bindAccount(userId, "google", googleId, email);
        }

        // Generate our system's token
        return sysUserTokenService.createToken(userId);
    }
}
