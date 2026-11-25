import json
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from datetime import timedelta

DATA_FILE = Path("/data/mod.json")

def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}

def save(data: dict):
    DATA_FILE.write_text(json.dumps(data, indent=2))

def get_guild(guild_id: int) -> dict:
    data = load()
    return data.setdefault(str(guild_id), {
        "cases": [],
        "notes": {},
        "stats": {},
        "mod_roles": [],
        "log_channel": None
    })

def get_mod_roles(guild_id: int) -> list[int]:
    return get_guild(guild_id).get("mod_roles", [])

def set_mod_roles(guild_id: int, role_ids: list[int]):
    data = load()
    guild = data.setdefault(str(guild_id), {})
    guild["mod_roles"] = role_ids
    save(data)

def get_log_channel(guild_id: int) -> int | None:
    return get_guild(guild_id).get("log_channel")

def set_log_channel(guild_id: int, channel_id: int | None):
    data = load()
    guild = data.setdefault(str(guild_id), {})
    if channel_id:
        guild["log_channel"] = channel_id
    else:
        guild.pop("log_channel", None)
    save(data)

def is_mod(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    allowed = get_mod_roles(interaction.guild_id)
    return any(role.id in allowed for role in interaction.user.roles)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def add_case(self, guild_id: int, action: str, target_id: int, mod_id: int, reason: str = None):
        data = load()
        guild = data.setdefault(str(guild_id), {"cases": [], "notes": {}, "stats": {}, "mod_roles": []})
        case_id = len(guild["cases"]) + 1
        guild["cases"].append({
            "id": case_id,
            "action": action,
            "target": target_id,
            "mod": mod_id,
            "reason": reason,
            "timestamp": discord.utils.utcnow().isoformat()
        })
        stats = guild["stats"].setdefault(str(mod_id), {})
        stats[action] = stats.get(action, 0) + 1
        save(data)
        return case_id

    async def announce(self, interaction: discord.Interaction, action: str, target: discord.Member | discord.User, reason: str = None, extra: str = ""):
        log_id = get_log_channel(interaction.guild_id)
        if log_id:
            channel = interaction.guild.get_channel(log_id)
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title=action.title(),
                    color=0xFF6B6B,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=False)
                embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                if extra:
                    embed.add_field(name="Details", value=extra, inline=False)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        try:
            dm = discord.Embed(
                title=f"You were {action} in {interaction.guild.name}",
                color=0xFF6B6B
            )
            if reason:
                dm.add_field(name="Reason", value=reason, inline=False)
            if extra:
                dm.add_field(name="Details", value=extra, inline=False)
            dm.set_footer(text="Contact staff if you think this was a mistake.")
            await target.send(embed=dm)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── MOD ROLE MANAGEMENT ─────────────────────────────────
    @app_commands.command(name="modrole_add", description="Allow a role to use mod commands")
    @app_commands.checks.has_permissions(administrator=True)
    async def modrole_add(self, interaction: discord.Interaction, role: discord.Role):
        roles = get_mod_roles(interaction.guild_id)
        if role.id not in roles:
            roles.append(role.id)
            set_mod_roles(interaction.guild_id, roles)
        await interaction.response.send_message(f"Added {role.mention} as a mod role.", ephemeral=True)

    @app_commands.command(name="modrole_remove", description="Remove a role from mod commands")
    @app_commands.checks.has_permissions(administrator=True)
    async def modrole_remove(self, interaction: discord.Interaction, role: discord.Role):
        roles = get_mod_roles(interaction.guild_id)
        if role.id in roles:
            roles.remove(role.id)
            set_mod_roles(interaction.guild_id, roles)
        await interaction.response.send_message(f"Removed {role.mention} from mod roles.", ephemeral=True)

    @app_commands.command(name="modrole_list", description="Show roles that can use mod commands")
    @app_commands.checks.has_permissions(administrator=True)
    async def modrole_list(self, interaction: discord.Interaction):
        roles = get_mod_roles(interaction.guild_id)
        if not roles:
            return await interaction.response.send_message("No mod roles set (admins only).", ephemeral=True)
        mentions = [f"<@&{rid}>" for rid in roles]
        await interaction.response.send_message("Mod roles:\n" + "\n".join(mentions), ephemeral=True)

    # ── MOD LOG CHANNEL ─────────────────────────────────────
    @app_commands.command(name="modlog", description="Set the public channel for mod action logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def modlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_log_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(f"Mod logs will post in {channel.mention}", ephemeral=True)

    @app_commands.command(name="modlog_off", description="Turn off public mod logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def modlog_off(self, interaction: discord.Interaction):
        set_log_channel(interaction.guild_id, None)
        await interaction.response.send_message("Public mod logs disabled.", ephemeral=True)

    # ── BAN / UNBAN / KICK ──────────────────────────────────
    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.check(is_mod)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.ban(reason=reason)
        case = self.add_case(interaction.guild_id, "ban", member.id, interaction.user.id, reason)
        await self.announce(interaction, "banned", member, reason)
        await interaction.response.send_message(f"Banned {member} (Case #{case})", ephemeral=True)

    @app_commands.command(name="unban", description="Unban by user ID")
    @app_commands.check(is_mod)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        user = await self.bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        self.add_case(interaction.guild_id, "unban", user.id, interaction.user.id)
        await self.announce(interaction, "unbanned", user)
        await interaction.response.send_message(f"Unbanned {user}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.check(is_mod)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.kick(reason=reason)
        case = self.add_case(interaction.guild_id, "kick", member.id, interaction.user.id, reason)
        await self.announce(interaction, "kicked", member, reason)
        await interaction.response.send_message(f"Kicked {member} (Case #{case})", ephemeral=True)

    # ── TIMEOUT ─────────────────────────────────────────────
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.check(is_mod)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason"):
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        case = self.add_case(interaction.guild_id, "timeout", member.id, interaction.user.id, reason)
        await self.announce(interaction, "timed out", member, reason, f"{minutes} minutes")
        await interaction.response.send_message(f"Timed out {member} for {minutes}m (Case #{case})", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove timeout")
    @app_commands.check(is_mod)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None)
        self.add_case(interaction.guild_id, "untimeout", member.id, interaction.user.id)
        await self.announce(interaction, "un-timed out", member)
        await interaction.response.send_message(f"Removed timeout from {member}", ephemeral=True)

    # ── WARN + HISTORY ──────────────────────────────────────
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.check(is_mod)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        case = self.add_case(interaction.guild_id, "warn", member.id, interaction.user.id, reason)
        await self.announce(interaction, "warned", member, reason)
        await interaction.response.send_message(f"Warned {member} (Case #{case})", ephemeral=True)

    @app_commands.command(name="history", description="View a user's moderation history")
    @app_commands.check(is_mod)
    async def history(self, interaction: discord.Interaction, user: discord.User):
        guild = get_guild(interaction.guild_id)
        cases = [c for c in guild["cases"] if c["target"] == user.id]
        if not cases:
            return await interaction.response.send_message("No cases found.", ephemeral=True)

        embed = discord.Embed(title=f"History for {user}", color=0xFF6B6B)
        for c in cases[-15:]:
            embed.add_field(
                name=f"Case #{c['id']} • {c['action']}",
                value=f"Reason: {c.get('reason', 'None')}\nMod: <@{c['mod']}>",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── NOTES ───────────────────────────────────────────────
    @app_commands.command(name="notes_add", description="Add a staff note")
    @app_commands.check(is_mod)
    async def notes_add(self, interaction: discord.Interaction, user: discord.User, note: str):
        data = load()
        guild = data.setdefault(str(interaction.guild_id), {})
        notes = guild.setdefault("notes", {}).setdefault(str(user.id), [])
        notes.append({"id": len(notes) + 1, "note": note, "mod": interaction.user.id})
        save(data)
        await interaction.response.send_message("Note added.", ephemeral=True)

    @app_commands.command(name="notes_view", description="View staff notes")
    @app_commands.check(is_mod)
    async def notes_view(self, interaction: discord.Interaction, user: discord.User):
        guild = get_guild(interaction.guild_id)
        notes = guild.get("notes", {}).get(str(user.id), [])
        if not notes:
            return await interaction.response.send_message("No notes.", ephemeral=True)
        text = "\n".join(f"**#{n['id']}** {n['note']} (by <@{n['mod']}>)" for n in notes)
        await interaction.response.send_message(text, ephemeral=True)

    # ── PURGE ───────────────────────────────────────────────
    @app_commands.command(name="purge", description="Purge recent messages")
    @app_commands.check(is_mod)
    async def purge(self, interaction: discord.Interaction, amount: int = 50):
        if amount > 1000:
            amount = 1000
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="purge_bots", description="Delete recent messages from bots")
    @app_commands.check(is_mod)
    async def purge_bots(self, interaction: discord.Interaction, amount: int = 100):
        if amount > 1000:
            amount = 1000
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author.bot)
        await interaction.followup.send(f"Deleted {len(deleted)} bot messages.", ephemeral=True)

    @app_commands.command(name="purge_users", description="Delete recent messages from humans")
    @app_commands.check(is_mod)
    async def purge_users(self, interaction: discord.Interaction, amount: int = 100):
        if amount > 1000:
            amount = 1000
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: not m.author.bot)
        await interaction.followup.send(f"Deleted {len(deleted)} user messages.", ephemeral=True)

    @app_commands.command(name="purge_text", description="Delete recent text-only messages")
    @app_commands.check(is_mod)
    async def purge_text(self, interaction: discord.Interaction, amount: int = 100):
        if amount > 1000:
            amount = 1000
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(
            limit=amount,
            check=lambda m: bool(m.content) and not m.embeds and not m.attachments and not m.stickers
        )
        await interaction.followup.send(f"Deleted {len(deleted)} text-only messages.", ephemeral=True)

    # ── MODSTATS ────────────────────────────────────────────
    @app_commands.command(name="modstats", description="See moderator action counts")
    @app_commands.check(is_mod)
    async def modstats(self, interaction: discord.Interaction):
        guild = get_guild(interaction.guild_id)
        stats = guild.get("stats", {})
        if not stats:
            return await interaction.response.send_message("No stats yet.", ephemeral=True)

        embed = discord.Embed(title="Mod Stats", color=0xA7C7E7)
        for mod_id, actions in stats.items():
            lines = [f"{action}: {count}" for action, count in actions.items()]
            embed.add_field(name=f"<@{mod_id}>", value="\n".join(lines), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
