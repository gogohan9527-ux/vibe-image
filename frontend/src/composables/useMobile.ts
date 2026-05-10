import { ref, onMounted, onUnmounted } from 'vue';

const BREAKPOINT = 768;

export function useIsMobile() {
  const isMobile = ref(
    typeof window !== 'undefined' ? window.innerWidth < BREAKPOINT : false,
  );

  function update() {
    isMobile.value = window.innerWidth < BREAKPOINT;
  }

  onMounted(() => window.addEventListener('resize', update));
  onUnmounted(() => window.removeEventListener('resize', update));

  return { isMobile };
}
