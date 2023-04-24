import asyncio
from faulthandler import disable

from discord.ui import View, Button
from uuid import uuid4
from discord import (
    Embed,
    ButtonStyle,
    Interaction,
    InteractionMessage,
    Message,
    WebhookMessage,
    ApplicationContext,
)
from typing import Any, Dict, Optional, Set, Union


class BetterView(View):
    """
    A subclass of view that is prepackaged with a check based on the context,
    and a one-time fade out implementation for buttons - the chosen button will
    remain in color whilst the rest will be grayed out. All the buttons are disabled
    after the first click.
    """

    embed: Optional[Embed] = None
    content: Optional[str] = None
    ephemeral: bool = False

    def __init__(
        self,
        timeout: int = 180,
        one_shot: bool = True,
        edit_on_shot: bool = False,
        add_deleter: bool = True,
        authors: Set[int] = set(),
        channel_id: Optional[int] = None,
        store_select_value: bool = False,
        default_select_value: Optional[Any] = None,
    ):
        """
        :param timeout: timeout for view
        :param one_shot: the view stops itself after any button has been clicked
                        once if True
        :param edit_on_shot: edits the view with all disabled items as an aftermath of
                             one shot (only relevant if this view is oneshot)
        :param add_deleter: adds a deleter button to the view, this simply calls add_deleter()
                            this can be used to alter the arrangement of the deleter
        :param authors: a list of authors that can interact with the view
        :param channel_id: a channel ID that the view lives inside
        :param store_select_value: a channel ID that the view lives inside
        :param default_select_value: a channel ID that the view lives inside
        """
        super().__init__(timeout=timeout)
        self.one_shot = one_shot
        self.edit_on_shot = edit_on_shot
        self.authors = authors
        self.channel_id = channel_id
        self.store_select_value = store_select_value
        self.message: Union[Message, WebhookMessage, InteractionMessage] = None  # type: ignore
        self.values = default_select_value

        self.__DELETER_ID = str(uuid4())
        self.__original_colors: Dict[str, ButtonStyle] = {
            self.__DELETER_ID: ButtonStyle.gray
        }
        self.__og_colors_set = False

        # Message references given by the interaction are kinda finiky and is not
        # present unless an interaction is triggered
        if add_deleter is True:
            self.add_deleter()

    @classmethod
    async def respond(
        cls,
        via: Union[ApplicationContext, Message, Interaction],
        *view_args,
        **view_kwargs,
    ):
        """
        Responds to a message, ApplicationContext or a Context with the View
        given.

        The view object is created internally - as a convinence feature, if the respondable has
        type alignment with a special argument or kwargument named ctx, it is automatically
        passed in to avoid having to pass in the same argument twice.
        """
        view = cls(*view_args, **view_kwargs)  # type: ignore
        if isinstance(via, ApplicationContext):
            if via.author:
                view.authors.add(via.author.id)
            view.channel_id = via.channel_id
            via = await via.respond(**view.prompt())

        if isinstance(via, (Message, WebhookMessage)):
            view.authors.add(via.author.id)
            view.channel_id = via.channel.id
            view.set_message(await via.edit(**view.prompt(edit=True)))
        elif isinstance(via, Interaction):
            if not view.channel_id:
                if via.user:
                    view.authors.add(via.user.id)
                view.channel_id = via.channel_id
                await via.response.edit_message(**view.prompt(edit=True))
            view.set_message(await via.original_message())
        else:
            raise TypeError(f"{via.__class__} is not respondable")

        return view

    def add_deleter(self):
        """
        Adds a deleter button to the view.

        :return:
        """
        self.add_item(
            Button(style=ButtonStyle.gray, custom_id=self.__DELETER_ID, emoji="🗑️")
        )

    def set_message(self, msg: Union[Message, WebhookMessage, InteractionMessage]):
        self.message = msg

    async def delete_initial_msg(self):
        """
        Deletes the initial message reference.
        """
        if self.message is None:
            raise TypeError(
                "initial message reference is not kept, make sure your interaction"
                " has a message and use respond when sending views"
            )
        if self.message.flags.ephemeral:
            await self.edit_initial_msg(view=self.disable_all_items())
        else:
            await self.message.delete()
            self.stop()

    async def interaction_check(
        self, interaction: Interaction, edit_later=False
    ) -> bool:
        """
        Impose one-time fadeout presets if the interaction is valid.

        edit_later: If false will edit itself immediately, else it will not. This will save
                    a few requests if there is deemed to be an edit right after a valid interaction
                    is recieved.
        """
        if interaction.user is None:
            return False

        loop = asyncio.get_running_loop()
        if self.authors and interaction.user.id not in self.authors:
            loop.create_task(
                interaction.response.send_message(
                    "Hey, you are not allowed to interact with this view!",
                    ephemeral=True,
                )
            )
            return False
        if self.store_select_value and interaction.data:
            self.values = interaction.data.get(
                "values", interaction.data.get("custom_id")
            )

        if interaction.data["custom_id"] == self.__DELETER_ID:  # type: ignore
            # We will stop the interaction inside the deleter,
            # this is because stopping this will prevent users
            # from dismissing the message if it is ephemeral.
            loop.create_task(self.delete_initial_msg())
            return True

        if self.one_shot:
            for item in self.children:
                item.disabled = True  # type: ignore
                if item.custom_id != interaction.data["custom_id"]:  # type: ignore
                    item.style = ButtonStyle.gray  # type: ignore

            if edit_later or self.edit_on_shot:
                loop.create_task(self.edit_initial_msg(view=self))

            self.stop()
        return True

    async def update_initial_msg(self):
        """
        Updates the initial message with it's own prompt.

        Same as doing BetterView.edit_initial_msg(**BetterView.prompt)
        """
        return await self.edit_initial_msg(**self.prompt())  # type: ignore

    async def edit_initial_msg(self, **kwargs):
        """
        Edits the initial message that the view had responded to.

        kwargs: Dict[str, Any] = a dictionary of keyword arguments that specifies the fields to be
                                edited
        """
        if self.message is None:
            raise TypeError(
                "initial message reference is not kept, make sure your interaction"
                " has a message and use respond when sending views"
            )
        else:
            await self.message.edit(**kwargs)

    def enable_all_items(self):
        """
        Enables all the children items.
        """
        for item in self.children:
            item.disabled = False  # type: ignore
            color = self.__original_colors.get(item.custom_id, None)  # type: ignore
            if color is not None:
                item.style = color  # type: ignore
        return self

    def disable_all_items(self):
        """
        Disables all the children items.
        """
        for item in self.children:
            item.disabled = True  # type: ignore
            item.style = ButtonStyle.gray  # type: ignore
        return self

    async def on_timeout(self):
        self.stop()
        await self.edit_initial_msg(view=self.disable_all_items())
        return await super().on_timeout()

    def prompt(self, edit: bool = False):
        """
        A property for views that returns a dictionary of message
        kwargs like embed and view. This is so that views have
        total control of what message and embed gets displayed with them.

        :return: dict
        """
        if not self.__og_colors_set:
            self.__original_colors.update(
                {
                    child.custom_id: child.style
                    for child in self.children
                    if isinstance(child, Button) and child.custom_id
                }
            )
            self.__og_colors_set = True
        kwds: Any = {"view": self}
        if self.embed:
            kwds["embed"] = self.embed
        if self.content:
            kwds["content"] = self.content
        if not edit:
            if self.ephemeral:
                kwds["ephemeral"] = self.ephemeral
        return kwds


class StatusButton(Button):
    def __init__(self, msg: str, ok: bool, disabled: bool):
        super().__init__(
            style=ButtonStyle.blurple if ok else ButtonStyle.danger,
            label=f"{'𝗢𝗞' if ok else '𝗘𝗥𝗥𝗢𝗥'}: {msg}",
        )
        self.disabled = disabled

    async def callback(self, interaction: Interaction):
        await interaction.response.edit_message(
            embed=Embed(title="You're a bad apple, you clicked the damn error.")
        )


class StatusView(BetterView):
    ephemeral = True

    def __init__(self, msg: str, desc: str, state: bool):
        super().__init__(add_deleter=False, edit_on_shot=True)
        self.state = state
        self.desc = desc
        self.msg = msg
        self.add_item(StatusButton(msg, ok=state, disabled=not bool(self.desc)))
        self.add_deleter()


class ErrorView(StatusView):
    def __init__(self, msg: str, desc: str = ""):
        super().__init__(msg, desc, False)


class OKView(StatusView):
    def __init__(self, msg: str, desc: str = ""):
        super().__init__(msg, desc, True)
