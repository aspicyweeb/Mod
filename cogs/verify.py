    @app_commands.command(name="setverify", description="Roles for unverified, 18+, creator, and female")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        unverified="Role people have before they verify",
        verified="18+ role",
        creator="Creator role",
        female="Female role",
    )
    async def setverify(
        self,
        interaction: discord.Interaction,
        unverified: discord.Role | None = None,
        verified: discord.Role | None = None,
        creator: discord.Role | None = None,
        female: discord.Role | None = None,
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this in the server.", ephemeral=True)
            return
        updates: dict[str, int] = {}
        shown: list[str] = []
        if unverified is not None:
            updates["unverified"] = unverified.id
            shown.append(f"unverified {unverified.mention}")
        if verified is not None:
            updates["18"] = verified.id
            shown.append(f"18+ {verified.mention}")
        if creator is not None:
            updates["creator"] = creator.id
            shown.append(f"creator {creator.mention}")
        if female is not None:
            updates["female"] = female.id
            shown.append(f"female {female.mention}")
        if not updates:
            await interaction.response.send_message("Pick at least one role.", ephemeral=True)
            return
        async with storage.lock:
            data = storage.load_obj("config.json")
            guild = str(interaction.guild_id)
            data.setdefault(guild, {})
            verify = data[guild].setdefault("verify", {})
            verify.update(updates)
            storage.save("config.json", data)
        await interaction.response.send_message("Verification set: " + ", ".join(shown), ephemeral=True)
