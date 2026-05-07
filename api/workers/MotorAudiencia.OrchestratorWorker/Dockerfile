FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["workers/MotorAudiencia.OrchestratorWorker/MotorAudiencia.OrchestratorWorker.csproj", "workers/MotorAudiencia.OrchestratorWorker/"]
COPY ["src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj", "src/MotorAudiencia.Infrastructure/"]
COPY ["src/MotorAudiencia.Application/MotorAudiencia.Application.csproj", "src/MotorAudiencia.Application/"]
COPY ["src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj", "src/MotorAudiencia.Domain/"]
RUN dotnet restore "workers/MotorAudiencia.OrchestratorWorker/MotorAudiencia.OrchestratorWorker.csproj"
COPY . .
RUN dotnet publish "workers/MotorAudiencia.OrchestratorWorker/MotorAudiencia.OrchestratorWorker.csproj" \
    -c Release -o /app/publish --no-restore

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "MotorAudiencia.OrchestratorWorker.dll"]
