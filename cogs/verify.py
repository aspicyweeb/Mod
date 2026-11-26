import json
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path

DATA_FILE = Path("/data/mod.json")


def load() -> dict:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save(data: dict):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def get_verify_cfg(guild_id: int) -> dict:
    data = load()
    return data.get(str(guild_id), {}).get("verify", {})


def set_verify_cfg(guild_id: int, cfg: dict):
    data = load()
    guild = data.setdefault(str(guild_id), {})
    guild["verify"] = cfg
    save(data)


def is_mod(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    data = load()
    allowed = data.get(str(interaction.guild_id), {}).get("mod_roles", [])
    return any(role.id in allowed for role in interaction.user.roles)


class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _give(self, interaction: discord.Interaction, member: discord.Member, key: str, label: str):
        cfg = get_verify_cfg(interaction.guild_id)
        role_id = cfg.get(key)
        if not role_id:
            await interaction.response.send_message(f"Set the {label} role first with /setverify.", ephemeral=True)
            return None

        role = interaction.guild.get_role(int(role_id))
        if role is None:
            await interaction.response.send_message(f"The {label} role was deleted. Run /setverify again.", ephemeral=True)
            return None

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(f"Move my role above {role.mention}.", ephemeral=True)
            return None

        try:
            await member.add_roles(role, reason=f"{label} by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(f"I can't assign {role.mention}. Move my role higher.", ephemeral=True)
            return None
        return role

    @app_commands.command(name="setverify", description="Set verification roles")
    @app_commands.checks.has_permissions(administrator=True)
    async def setverify(
        self,
        interaction: discord.Interaction,
        role18: discord.Role = None,
        creator: discord.Role = None,
        female: discord.Role = None,
        unverified: discord.Role = None,
        autorole: discord.Role = None,
    ):
        cfg = get_verify_cfg(interaction.guild_id)
        if role18:
            cfg["18"] = role18.id
        if creator:
            cfg["creator"] = creator.id
        if female:
            cfg["female"] = female.id
        if unverified:
            cfg["unverified"] = unverified.id
        if autorole:
            cfg["autorole"] = autorole.id
        set_verify_cfg(interaction.guild_id, cfg)

        parts = []
        if role18:
            parts.append(f"18+: {role18.mention}")
        if creator:
            parts.append(f"Creator: {creator.mention}")
        if female:
            parts.append(f"Female: {female.mention}")
        if unverified:
            parts.append(f"Unverified: {unverified.mention}")
        if autorole:
            parts.append(f"Autorole: {autorole.mention}")
        await interaction.response.send_message("Updated:\n" + "\n".join(parts) if parts else "No changes.", ephemeral=True)

    @app_commands.command(name="verify18", description="Verify a member as 18+ and remove unverified")
    @app_commands.check(is_mod)
    async def verify18(self, interaction: discord.Interaction, member: discord.Member):
        role = await self._give(interaction, member, "18", "18+")
        if role is None:
            return

        note = ""
        cfg = get_verify_cfg(interaction.guild_id)
        unverified_id = cfg.get("unverified")
        if unverified_id:
            unverified = interaction.guild.get_role(int(unverified_id))
            if unverified and unverified in member.roles:
                try:
                    await member.remove_roles(unverified, reason="removed unverified on 18+ verify")
                except discord.Forbidden:
                    note = " Couldn't remove the unverified role."
        await interaction.response.send_message(f"Verified {member.mention} as 18+.{note}", ephemeral=True)

    @app_commands.command(name="verifycreator", description="Verify a member as creator")
    @app_commands.check(is_mod)
    async def verifycreator(self, interaction: discord.Interaction, member: discord.Member):
        role = await self._give(interaction, member, "creator", "creator")
        if role is None:
            return
        await interaction.response.send_message(f"Gave {member.mention} the creator role.", ephemeral=True)

    @app_commands.command(name="verifyfemale", description="Verify a member as female")
    @app_commands.check(is_mod)
    async def verifyfemale(self, interaction: discord.Interaction, member: discord.Member):
        role = await self._give(interaction, member, "female", "female")
        if role is None:
            return
        await interaction.response.send_message(f"Gave {member.mention} the female role.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = get_verify_cfg(member.guild.id)
        rid = cfg.get("autorole")
        if not rid:
            return
        role = member.guild.get_role(int(rid))
        if role is None:
            return
        try:
            await member.add_roles(role, reason="autorole")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))