ARG acr_version=0.11
FROM mcr.microsoft.com/acr/acr-cli:$acr_version as build
ARG copa_version=0.6.2
ARG trivy_version=0.51.4
RUN tdnf check-update \
    && tdnf --refresh install -y \
        tar
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /tmp/bin v${trivy_version}
RUN curl --retry 5 -fsSL -o copa.tar.gz https://github.com/project-copacetic/copacetic/releases/download/v${copa_version}/copa_${copa_version}_linux_amd64.tar.gz && \
    tar -zxvf copa.tar.gz && \
    cp copa /tmp/bin/
RUN cp /usr/bin/acr /tmp/bin/
COPY docker-entrypoint.sh /tmp/bin/
RUN chmod +x /tmp/bin/docker-entrypoint.sh

FROM mcr.microsoft.com/cbl-mariner/base/core:2.0
LABEL maintainer=acr-feedback@microsoft.com
RUN tdnf check-update \
    && tdnf --refresh install -y \
        ca-certificates-microsoft \
        moby-cli moby-containerd \
    && tdnf clean all
COPY --from=build /tmp/bin/ /usr/bin/
ENTRYPOINT ["docker-entrypoint.sh"]