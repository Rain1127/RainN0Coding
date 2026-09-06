FROM maven:3.9.11-eclipse-temurin-23 AS build

WORKDIR /src
COPY pom.xml ./
RUN mvn -B -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 app \
    && mkdir -p /app/tmp \
    && chown -R app:app /app
WORKDIR /app
COPY --from=build /src/target/RainN0Coding-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8123
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD curl -fsS http://127.0.0.1:8123/api/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
