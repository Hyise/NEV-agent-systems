<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { RouterView, useRouter } from "vue-router";

const router = useRouter();
const routeError = ref<Error | null>(null);
const removeErrorListener = router.onError((error) => {
  routeError.value = error;
});
const removeAfterEach = router.afterEach(() => {
  routeError.value = null;
});

function reloadApplication() {
  window.location.reload();
}

async function returnToPlatform() {
  routeError.value = null;
  await router.replace("/");
}

onBeforeUnmount(() => {
  removeErrorListener();
  removeAfterEach();
});
</script>

<template>
  <main v-if="routeError" class="module-load-error" role="alert">
    <p class="platform-kicker">模块未能载入</p>
    <h1>模块加载失败</h1>
    <p>
      本机页面资源没有完整加载。可以重新加载当前页面，或返回平台选择其他系统。
    </p>
    <div class="module-load-error__actions">
      <button class="platform-action" type="button" @click="reloadApplication">
        重新加载
      </button>
      <button
        class="platform-action platform-action--secondary"
        type="button"
        @click="returnToPlatform"
      >
        返回平台
      </button>
    </div>
  </main>
  <RouterView v-else v-slot="{ Component, route }">
    <KeepAlive>
      <component
        :is="Component"
        v-if="route.meta.keepAlive"
        :key="route.name"
      />
    </KeepAlive>
    <component :is="Component" v-if="!route.meta.keepAlive" :key="route.name" />
  </RouterView>
</template>
