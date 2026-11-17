FROM mcr.microsoft.com/acr/acr-cli:0.21@sha256:7e739037a5ce52b1456a2cb89ad6d1e7e1a7c7ddc0ad39e261bc9b4c6dd93603 AS base
ARG TARGETARCH=amd64
RUN test "$TARGETARCH" = amd64

FROM base AS tools
RUN tdnf --refresh install -y curl tar gzip && tdnf clean all
WORKDIR /work
COPY tools.lock install-tools.sh ./
RUN bash install-tools.sh tools.lock /out

FROM base
LABEL maintainer=acr-feedback@microsoft.com
ENV EXPERIMENTAL_BUILDKIT_SOURCE_POLICY="/app/source-policy.json"
COPY source-policy.json /app/source-policy.json
RUN tdnf --refresh upgrade -y \
    && tdnf --refresh install -y \
        bash-5.2.15-3.azl3 \
        coreutils-9.4-7.azl3 \
        docker-cli-25.0.7-6.azl3 \
        jq-1.7.1-8.azl3 \
        skopeo-1.14.4-15.azl3 \
        tar gzip \
    && tdnf clean all
COPY --from=tools /out/bin/ /usr/bin/
COPY --from=tools /out/licenses/ /usr/share/licenses/cssc/
COPY tools.lock /app/tools.lock
COPY docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
COPY smoke-test.sh /usr/local/bin/cssc-smoke-test
RUN chmod 0755 /usr/bin/docker-entrypoint.sh /usr/local/bin/cssc-smoke-test \
    && rpm -qa > /app/rpm-packages.txt \
    && sort -o /app/rpm-packages.txt /app/rpm-packages.txt
ENTRYPOINT ["docker-entrypoint.sh"]
