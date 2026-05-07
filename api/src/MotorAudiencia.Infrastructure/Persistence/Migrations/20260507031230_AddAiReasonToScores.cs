using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace MotorAudiencia.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddAiReasonToScores : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "ai_reason",
                table: "scores",
                type: "character varying(500)",
                maxLength: 500,
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "updated_at",
                table: "scores",
                type: "timestamp with time zone",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "ai_reason",
                table: "scores");

            migrationBuilder.DropColumn(
                name: "updated_at",
                table: "scores");
        }
    }
}
