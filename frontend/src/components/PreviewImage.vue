<script setup lang="ts">
import { computed } from 'vue';
import { ElIcon, ElImage } from 'element-plus';
import { Picture } from '@element-plus/icons-vue';

const props = withDefaults(
  defineProps<{
    src?: string | null;
    alt?: string;
    fit?: 'fill' | 'contain' | 'cover' | 'none' | 'scale-down';
    preview?: boolean;
  }>(),
  {
    src: null,
    alt: 'image',
    fit: 'cover',
    preview: true,
  },
);

const previewList = computed(() => (props.preview && props.src ? [props.src] : []));
</script>

<template>
  <div class="preview-image" :class="{ 'is-empty': !src }">
    <ElImage
      v-if="src"
      class="preview-image__img"
      :src="src"
      :alt="alt"
      :fit="fit"
      :preview-src-list="previewList"
      preview-teleported
      hide-on-click-modal
    >
      <template #error>
        <div class="preview-image__placeholder">
          <ElIcon :size="20" color="#cbd5e1"><Picture /></ElIcon>
        </div>
      </template>
    </ElImage>
    <div v-else class="preview-image__placeholder">
      <ElIcon :size="20" color="#cbd5e1"><Picture /></ElIcon>
    </div>
  </div>
</template>

<style scoped>
.preview-image {
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: grid;
  place-items: center;
}

.preview-image:not(.is-empty) {
  cursor: zoom-in;
}

.preview-image__img {
  width: 100%;
  height: 100%;
  display: block;
}

.preview-image__img :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
}

.preview-image__placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
}
</style>
