package com.rain.rainn0coding.model.entity;

import com.mybatisflex.annotation.Column;
import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import java.io.Serializable;
import java.time.LocalDateTime;

import java.io.Serial;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 *  实体类。
 *
 * @author <a>Rain</a>
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("app_version")
public class AppVersion implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 版本记录ID
     */
    @Id(keyType = KeyType.Auto)
    private Long id;

    /**
     * 关联应用ID
     */
    @Column("app_id")
    private Long appId;

    /**
     * 版本号（递增）
     */
    @Column("version_number")
    private Integer versionNumber;

    /**
     * 代码内容（或文件路径，大文件建议存对象存储）
     */
    @Column("code_content")
    private String codeContent;

    /**
     * 版本修改说明
     */
    @Column("description")
    private String description;

    /**
     * 版本创建时间
     */
    @Column("create_time")
    private LocalDateTime createTime;

}
