"""
User account operators
"""
from typing import cast
import bpy
from bpy.types import Context
from bpy_speckle.functions import _report
from bpy_speckle.clients import speckle_clients
from bpy_speckle.properties.scene import SpeckleCommitObject, SpeckleSceneSettings, SpeckleUserObject, get_speckle
from specklepy.api.client import SpeckleClient
from specklepy.api.models import Stream
from specklepy.api.credentials import get_local_accounts

class ResetUsers(bpy.types.Operator):
    """
    Reset loaded users
    """

    bl_idname = "speckle.users_reset"
    bl_label = "Reset users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        self.reset_ui(context)

        bpy.context.view_layer.update()
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}

    @staticmethod
    def reset_ui(context: Context):
        speckle = get_speckle(context)

        speckle.users.clear()
        speckle_clients.clear()

class LoadUsers(bpy.types.Operator):
    """
    Load all users from local user database
    """

    bl_idname = "speckle.users_load"
    bl_label = "Load users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        _report("Loading users...")

        speckle = cast(SpeckleSceneSettings, context.scene.speckle) #type: ignore
        users = speckle.users

        ResetUsers.reset_ui(context)

        profiles = get_local_accounts()
        active_user_index = 0

        for profile in profiles:
            user = users.add()
            user.server_name = profile.serverInfo.name or "Speckle Server"
            user.server_url = profile.serverInfo.url
            user.id = profile.userInfo.id
            user.name = profile.userInfo.name
            user.email = profile.userInfo.email
            user.company = profile.userInfo.company or ""
            try:
                url = profile.serverInfo.url
                assert(url)
                client = SpeckleClient(
                    host=url,
                    use_ssl="https" in url,
                )
                client.authenticate_with_account(profile)
                speckle_clients.append(client)
            except Exception as ex:
                _report(ex)
                users.remove(len(users) - 1)
            if profile.isDefault:
                active_user_index = len(users) - 1

        speckle.active_user = str(active_user_index)
        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def add_user_stream(user: SpeckleUserObject, stream: Stream):
    s = user.streams.add()
    s.name = stream.name
    s.id = stream.id
    s.description = stream.description

    if not stream.branches:
        return

    # branches = [branch for branch in stream.branches.items if branch.name != "globals"]
    for b in stream.branches.items:
        branch = s.branches.add()
        branch.name = b.name

        if not b.commits:
            continue

        for c in b.commits.items:
            commit: SpeckleCommitObject = branch.commits.add()
            commit.id = commit.name = c.id
            commit.message = c.message or ""
            commit.author_name = c.authorName
            commit.author_id = c.authorId
            commit.created_at = c.createdAt.strftime("%Y-%m-%d %H:%M:%S.%f%Z") if c.createdAt else ""
            commit.source_application = str(c.sourceApplication)
            commit.referenced_object = c.referencedObject

    if hasattr(s, "baseProperties"):
        s.units = stream.baseProperties.units # type: ignore
    else:
        s.units = "Meters"


class LoadUserStreams(bpy.types.Operator):
    """
    Load all available streams for active user user
    """

    bl_idname = "speckle.load_user_streams"
    bl_label = "Load user streams"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "(Re)load all available user streams"

    def execute(self, context):
        try:
            self.add_stream_from_url(context)
            return {"FINISHED"}
        except Exception as ex:
            _report(f"{self.bl_idname} failed: {ex}")
            return {"CANCELLED"} 
        
    def add_stream_from_url(self, context: Context) -> None:
        speckle = get_speckle(context)

        user = speckle.validate_user_selection()

        client = speckle_clients[int(speckle.active_user)]

        try:
            streams = client.stream.list(stream_limit=20)
        except Exception as e:
            _report(f"Failed to retrieve streams: {e}")
            return
        if not streams:
            _report("Failed to retrieve streams.")
            return

        user.streams.clear()

        default_units = "Meters"

        for s in streams:
            assert(s.id)
            sstream = client.stream.get(id=s.id, branch_limit=20)
            add_user_stream(user, sstream)

        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

