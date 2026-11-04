FROM mcr.microsoft.com/azure-cli:2.92.0-azurelinux3.0
LABEL maintainer=acr-feedback@microsoft.com
RUN tdnf --refresh install -y ca-certificates-microsoft \
    && tdnf clean all
CMD [ "--version" ]
ENTRYPOINT [ "az" ]