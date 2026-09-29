import {
  createRouter,
  type RouteComponent,
  type Router,
  type RouterHistory,
} from "vue-router";

type LazyRouteComponent = () => Promise<
  RouteComponent | { default: RouteComponent }
>;

export interface PlatformRouteComponents {
  home: RouteComponent | LazyRouteComponent;
  mcdm: RouteComponent | LazyRouteComponent;
  adaptive: RouteComponent | LazyRouteComponent;
}

export function createPlatformRouter(
  history: RouterHistory,
  components: PlatformRouteComponents,
): Router {
  return createRouter({
    history,
    routes: [
      {
        path: "/",
        name: "platform-home",
        component: components.home,
      },
      {
        path: "/mcdm",
        name: "mcdm",
        component: components.mcdm,
        meta: { keepAlive: true },
      },
      {
        path: "/adaptive",
        name: "adaptive",
        component: components.adaptive,
      },
      {
        path: "/:pathMatch(.*)*",
        redirect: "/",
      },
    ],
  });
}
