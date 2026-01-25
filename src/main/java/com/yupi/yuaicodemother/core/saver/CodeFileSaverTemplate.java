package com.yupi.yuaicodemother.core.saver;

import cn.hutool.core.io.FileUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import com.yupi.yuaicodemother.constant.AppConstant;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.model.enums.CodeGenTypeEnum;

import java.io.File;
import java.nio.charset.StandardCharsets;


/**
 * 抽象代码文件保存器模板类
 */
public abstract class CodeFileSaverTemplate<T> {

    //文件保存根目录
    private static final String FILE_SAVE_ROOT_DIR = AppConstant.CODE_OUTPUT_ROOT_DIR;


     /**
      * 模板方法：保存代码文件流程
      * @param appid 应用id
      * @param result 代码结果对象
      * @return 保存的代码目录
      */
    public final File saveCode(T result,Long appid){
        //1.验证输入
        validateInput(result);
        //2.唯一目录
        String baseDirPath = buildUniqueDir(appid);
        //3.保存文件，具体实现交给子类
        saveFiles(result,baseDirPath);
        //4.返回文件对象
        return new File(baseDirPath);
    }

    /**
     * 保存单个文件
     * @param dirPath  目录路径
     * @param filename 文件名
     * @param content  文件内容
     */
    public final void writeToFile(String dirPath, String filename, String content) {
        if (StrUtil.isNotBlank(content)){
            // 构建文件路径
            String filePath = dirPath + File.separator + filename;
            FileUtil.writeString(content,filePath, StandardCharsets.UTF_8);
        }
    }

    /**
     * 验证输入参数是否为空
     * @param result 代码结果对象
     */
    protected void validateInput(T result) {
        if(result == null){
            throw new BusinessException(ErrorCode.SYSTEM_ERROR,"代码结果对象不为空");
        }
    }

    /**
     * 构建文件的唯一路径(tmp/code_output/bizType_雪花ID)
     * @param appid 应用id
     * @return 目录路径
     */
    protected String buildUniqueDir(Long appid){
        // 验证应用id是否为空
        if(appid == null){
            throw new BusinessException(ErrorCode.PARAMS_ERROR,"应用id不能为空");
        }
        String codeType = getCodeType().getValue();
        String uniqueDirName = StrUtil.format("{}_{}",codeType, appid);
        String dirPath = FILE_SAVE_ROOT_DIR + File.separator + uniqueDirName;
        FileUtil.mkdir(dirPath);
        return dirPath;
    }

    /**
     * 保存文件的具体实现，由子类实现
     * @param result 代码结果对象
     * @param baseDirPath 唯一目录路径
     */
    protected abstract void saveFiles(T result, String baseDirPath);

     /**
      * 获取代码类型
      * @return 代码类型枚举
      */
    protected abstract CodeGenTypeEnum getCodeType();
}
