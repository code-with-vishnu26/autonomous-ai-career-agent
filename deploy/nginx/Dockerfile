# Edge reverse-proxy image (Phase 59, ADR-0076). Deliberately its own tiny
# Dockerfile (not a shared base with Dockerfile.frontend) so it can be
# rebuilt/redeployed independently of the frontend's static build.

FROM nginx:1.27-alpine

RUN addgroup -S career-agent && adduser -S career-agent -G career-agent

COPY edge.conf /etc/nginx/conf.d/default.conf
COPY edge-nginx.conf /etc/nginx/nginx.conf

RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R career-agent:career-agent /var/cache/nginx /var/run /var/log/nginx /etc/nginx

USER career-agent

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:80/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
