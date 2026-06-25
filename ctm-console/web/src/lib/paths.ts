const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');

export function appHref(path: string) {
  if (!path.startsWith('/')) return path;
  return `${basePath}${path}` || path;
}
