package com.yupi.yuaicodemother.service;


public interface ScreenshotService {

    /**
     * 通用的截图服务，可以得到访问地址
     * @param webUrl 网页URL
     * @return 截图访问地址
     */
    String generateAndUploadScreenshot(String webUrl);

}
