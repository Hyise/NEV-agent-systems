import {
  createRouter,
  type RouteComponent,
  type Router,
  type RouterHistory,
} from "vue-router";

type LazyRouteComponent = () => Promise<
  RouteComponent | { default: RouteComponent }
>;

export type McdmIntent = "criteria-discovery" | "review-annotation";
export type CollectionIntent = "sales-gap" | "review-date-gap";

export function parseMcdmIntent(value: unknown): McdmIntent | null {
  return value === "criteria-discovery" || value === "review-annotation"
    ? value
    : null;
}

export function parseCollectionIntent(value: unknown): CollectionIntent | null {
  return value === "sales-gap" || value === "review-date-gap" ? value : null;
}

export interface PlatformRouteComponents {
  home: RouteComponent | LazyRouteComponent;
  collection: RouteComponent | LazyRouteComponent;
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
        path: "/collection",
        name: "collection",
        component: components.collection,
        meta: { keepAlive: true },
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
