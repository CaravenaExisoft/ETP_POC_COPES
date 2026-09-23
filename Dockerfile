# Motor ETL PMC como Azure Container Apps Job (prompt seccion 15): trabajo
# batch finito, sin servidor web, sin ingress, proceso no root.

FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.12-slim

RUN groupadd --system etl && useradd --system --gid etl --create-home --home-dir /home/etl etl

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/etl-pmc /usr/local/bin/etl-pmc
COPY --from=build /usr/local/bin/compare-adf /usr/local/bin/compare-adf
COPY --from=build /usr/local/bin/generate-fixture /usr/local/bin/generate-fixture

USER etl
WORKDIR /home/etl

# Sin ENTRYPOINT fijo con manifiesto embebido: ADF (o el comando manual de
# Container Apps Job) provee --manifest en cada ejecucion (prompt seccion 4).
ENTRYPOINT ["etl-pmc"]
CMD ["run", "--help"]
