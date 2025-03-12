ARG acr_version=0.15
ARG oras_version=1.2.0
FROM ghcr.io/oras-project/oras:v${oras_version} as build
ARG copa_version=0.10.0
ARG trivy_version=0.60.0
ARG syft_version=1.11.1
RUN apk add curl tar gzip
RUN curl --retry 5 -fsSL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /tmp/bin v${syft_version}
RUN curl --retry 5 -fsSL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /tmp/bin v${trivy_version}
RUN curl --retry 5 -fsSL -o copa.tar.gz https://github.com/project-copacetic/copacetic/releases/download/v${copa_version}/copa_${copa_version}_linux_amd64.tar.gz && \
    tar -zxvf copa.tar.gz && \
    cp copa /tmp/bin/
COPY docker-entrypoint.sh /tmp/bin/
RUN chmod +x /tmp/bin/docker-entrypoint.sh & cp /bin/oras /tmp/bin/
 

FROM mcr.microsoft.com/acr/acr-cli:${acr_version}
LABEL maintainer=acr-feedback@microsoft.com
ENV EXPERIMENTAL_BUILDKIT_SOURCE_POLICY="/app/source-policy.json"
COPY source-policy.json /app/source-policy.json
RUN tdnf check-update \
    && tdnf --refresh install -y \
        ca-certificates-microsoft \
        moby-cli moby-containerd jq\
    && tdnf clean all
COPY --from=build /tmp/bin/ /usr/bin/
ENTRYPOINT ["docker-entrypoint.sh"]
