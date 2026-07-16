<script setup lang="ts">
const theme = {
  token: {
    colorPrimary: '#4f46e5',
    colorSuccess: '#15803d',
    colorError: '#dc2626',
    colorText: '#182034',
    colorTextSecondary: '#5d677a',
    colorBorder: '#d8deea',
    colorBgLayout: '#f4f6fb',
    borderRadius: 12,
    controlHeight: 44,
    fontSize: 16,
    fontFamily: '"IBM Plex Sans", "Noto Sans SC", "Microsoft YaHei UI", system-ui, sans-serif',
    motionDurationFast: '0.18s',
    motionDurationMid: '0.20s',
  },
}
</script>

<template>
  <a-config-provider :theme="theme">
    <router-view />
  </a-config-provider>
</template>
