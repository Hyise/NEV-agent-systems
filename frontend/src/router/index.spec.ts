import { defineComponent, h } from "vue";
import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";
import { createPlatformRouter } from "./index";

const routeComponents = {
  home: defineComponent(() => () => h("div", "platform")),
  mcdm: defineComponent(() => () => h("div", "mcdm")),
  adaptive: defineComponent(() => () => h("div", "adaptive")),
};

describe("createPlatformRouter", () => {
  it.each([
    ["/", "platform-home"],
    ["/mcdm", "mcdm"],
    ["/adaptive", "adaptive"],
  ])("resolves %s to %s", (path, routeName) => {
    const router = createPlatformRouter(createMemoryHistory(), routeComponents);

    expect(router.resolve(path).name).toBe(routeName);
  });

  it("keeps only the MCDM module alive", () => {
    const router = createPlatformRouter(createMemoryHistory(), routeComponents);

    expect(router.resolve("/mcdm").meta.keepAlive).toBe(true);
    expect(router.resolve("/").meta.keepAlive).not.toBe(true);
    expect(router.resolve("/adaptive").meta.keepAlive).not.toBe(true);
  });

  it("redirects unknown paths to the platform entrance", async () => {
    const router = createPlatformRouter(createMemoryHistory(), routeComponents);

    await router.push("/missing");
    await router.isReady();

    expect(router.currentRoute.value.name).toBe("platform-home");
    expect(router.currentRoute.value.path).toBe("/");
  });
});
