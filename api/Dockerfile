FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app
EXPOSE 5000
ENV ASPNETCORE_URLS=http://+:5000

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["src/MotorAudiencia.API/MotorAudiencia.API.csproj", "src/MotorAudiencia.API/"]
COPY ["src/MotorAudiencia.Application/MotorAudiencia.Application.csproj", "src/MotorAudiencia.Application/"]
COPY ["src/MotorAudiencia.Infrastructure/MotorAudiencia.Infrastructure.csproj", "src/MotorAudiencia.Infrastructure/"]
COPY ["src/MotorAudiencia.Domain/MotorAudiencia.Domain.csproj", "src/MotorAudiencia.Domain/"]
RUN dotnet restore "src/MotorAudiencia.API/MotorAudiencia.API.csproj"
COPY . .
RUN dotnet publish "src/MotorAudiencia.API/MotorAudiencia.API.csproj" -c Release -o /app/publish --no-restore

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "MotorAudiencia.API.dll"]
