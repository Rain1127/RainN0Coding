package com.rain.rainn0coding.service.impl;

import cn.dev33.satoken.stp.StpUtil;
import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.crypto.digest.BCrypt;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.rain.rainn0coding.exception.BusinessException;
import com.rain.rainn0coding.exception.ErrorCode;
import com.rain.rainn0coding.mapper.UserMapper;
import com.rain.rainn0coding.model.dto.user.UserQueryRequest;
import com.rain.rainn0coding.model.entity.User;
import com.rain.rainn0coding.model.enums.UserRoleEnum;
import com.rain.rainn0coding.model.vo.LoginUserVO;
import com.rain.rainn0coding.model.vo.UserVO;
import com.rain.rainn0coding.service.UserService;
import com.rain.rainn0coding.utils.SqlSafetyUtils;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Service;
import org.springframework.util.DigestUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
            "id", "userAccount", "userName", "userRole", "createTime", "updateTime"
    );

    @Override
    public long userRegister(String userAccount, String userPassword, String checkPassword) {
        if (StrUtil.hasBlank(userAccount, userPassword, checkPassword)) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "参数为空");
        }
        if (userAccount.length() < 4) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "账号长度不能小于4位");
        }
        if (userPassword.length() < 8 || checkPassword.length() < 8) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "密码长度不能小于8位");
        }
        if (!userPassword.equals(checkPassword)) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "两次输入的密码不一致");
        }
        QueryWrapper queryWrapper = new QueryWrapper();
        queryWrapper.eq("userAccount", userAccount);
        long count = this.mapper.selectCountByQuery(queryWrapper);
        if (count > 0) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "账号已存在");
        }
        User user = new User();
        user.setUserAccount(userAccount);
        user.setUserPassword(getEncryptPassword(userPassword));
        user.setUserName("sb");
        user.setUserRole(UserRoleEnum.USER.getValue());
        boolean saveResult = this.save(user);
        if (!saveResult) {
            throw new BusinessException(ErrorCode.OPERATION_ERROR, "用户注册失败");
        }
        return user.getId();
    }

    @Override
    public LoginUserVO getLoginUserVO(User user) {
        if (user == null) {
            return null;
        }
        LoginUserVO loginUserVO = new LoginUserVO();
        BeanUtil.copyProperties(user, loginUserVO);
        return loginUserVO;
    }

    @Override
    public User getLoginUser(HttpServletRequest request) {
        long userId;
        try {
            userId = StpUtil.getLoginIdAsLong();
        } catch (Exception e) {
            throw new BusinessException(ErrorCode.NOT_LOGIN_ERROR);
        }
        User currentUser = this.getById(userId);
        if (currentUser == null) {
            throw new BusinessException(ErrorCode.NOT_LOGIN_ERROR);
        }
        return currentUser;
    }

    @Override
    public UserVO getUserVO(User user) {
        if (user == null) {
            return null;
        }
        UserVO userVO = new UserVO();
        BeanUtil.copyProperties(user, userVO);
        return userVO;
    }

    @Override
    public List<UserVO> getUserVOList(List<User> userList) {
        if (CollUtil.isEmpty(userList)) {
            return new ArrayList<>();
        }
        return userList.stream().map(this::getUserVO).collect(Collectors.toList());
    }

    @Override
    public boolean userLogout(HttpServletRequest request) {
        if (!StpUtil.isLogin()) {
            throw new BusinessException(ErrorCode.OPERATION_ERROR, "用户未登录");
        }
        StpUtil.logout();
        return true;
    }

    @Override
    public QueryWrapper getQueryWrapper(UserQueryRequest userQueryRequest) {
        if (userQueryRequest == null) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "请求参数为空");
        }
        Long id = userQueryRequest.getId();
        String userAccount = userQueryRequest.getUserAccount();
        String userName = userQueryRequest.getUserName();
        String userProfile = userQueryRequest.getUserProfile();
        String userRole = userQueryRequest.getUserRole();
        String sortField = userQueryRequest.getSortField();
        String sortOrder = userQueryRequest.getSortOrder();
        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq("id", id)
                .eq("userRole", userRole)
                .like("userAccount", userAccount)
                .like("userName", userName)
                .like("userProfile", userProfile);
        String safeSortField = SqlSafetyUtils.safeSortField(sortField, ALLOWED_SORT_FIELDS);
        if (safeSortField != null) {
            queryWrapper.orderBy(safeSortField, "ascend".equals(sortOrder));
        }
        return queryWrapper;
    }

    @Override
    public LoginUserVO userLogin(String userAccount, String userPassword, HttpServletRequest request) {
        if (StrUtil.hasBlank(userAccount, userPassword)) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "参数为空");
        }
        if (userAccount.length() < 4) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "账号长度不能小于4位");
        }
        if (userPassword.length() < 8) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "密码长度不能小于8位");
        }
        QueryWrapper queryWrapper = new QueryWrapper();
        queryWrapper.eq("userAccount", userAccount);
        User user = this.mapper.selectOneByQuery(queryWrapper);
        if (user == null || !matchesPassword(userPassword, user.getUserPassword())) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "用户不存在或密码错误");
        }
        if (getLegacyEncryptPassword(userPassword).equals(user.getUserPassword())) {
            User updateUser = new User();
            updateUser.setId(user.getId());
            updateUser.setUserPassword(getEncryptPassword(userPassword));
            this.updateById(updateUser);
        }
        StpUtil.login(user.getId());
        return this.getLoginUserVO(user);
    }

    @Override
    public String getEncryptPassword(String userPassword) {
        return BCrypt.hashpw(userPassword, BCrypt.gensalt());
    }

    private boolean matchesPassword(String rawPassword, String encryptedPassword) {
        if (StrUtil.isBlank(encryptedPassword)) {
            return false;
        }
        if (encryptedPassword.startsWith("$2")) {
            return BCrypt.checkpw(rawPassword, encryptedPassword);
        }
        return getLegacyEncryptPassword(rawPassword).equals(encryptedPassword);
    }

    private String getLegacyEncryptPassword(String userPassword) {
        final String salt = "rain";
        return DigestUtils.md5DigestAsHex((salt + userPassword).getBytes());
    }
}
