package com.rain.rainn0coding.service.impl;

import com.rain.rainn0coding.mapper.IntentConfigMapper;
import com.rain.rainn0coding.model.entity.IntentConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class IntentConfigServiceImplTest {

    @Mock
    private IntentConfigMapper intentConfigMapper;

    private IntentConfigServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new IntentConfigServiceImpl();
        ReflectionTestUtils.setField(service, "intentConfigMapper", intentConfigMapper);
    }

    @Test
    void blankTreeDeletesExistingCustomizationInsteadOfKeepingAnEmptyRecord() {
        IntentConfig existing = new IntentConfig();
        existing.setId(42L);
        existing.setTreeJson("[{\"key\":\"old\",\"title\":\"Old\"}]");
        when(intentConfigMapper.selectOneByQuery(any())).thenReturn(existing);

        service.saveCustomTree("", 0L);

        verify(intentConfigMapper).deleteById(42L);
        verify(intentConfigMapper, never()).update(any());
    }
}
