import pytest

import idom


async def test_must_be_rendering_in_layout_to_use_hooks():
    @idom.element
    async def SimpleElementWithHook():
        idom.hooks.use_state(None)
        return idom.html.div()

    with pytest.raises(RuntimeError, match="No life cycle hook is active"):
        await SimpleElementWithHook().render()

    async with idom.Layout(SimpleElementWithHook()) as layout:
        await layout.render()


async def test_simple_stateful_element():
    @idom.element
    async def SimpleStatefulElement():
        index, set_index = idom.hooks.use_state(0)
        set_index(index + 1)
        return idom.html.div(index)

    sse = SimpleStatefulElement()

    async with idom.Layout(sse) as layout:
        assert (await layout.render()).new[sse.id] == {
            "tagName": "div",
            "children": [{"data": "0", "type": "str"}],
        }
        assert (await layout.render()).new[sse.id] == {
            "tagName": "div",
            "children": [{"data": "1", "type": "str"}],
        }
        assert (await layout.render()).new[sse.id] == {
            "tagName": "div",
            "children": [{"data": "2", "type": "str"}],
        }


def test_use_state_with_constructor(driver, display, driver_wait):
    constructor_call_count = idom.Var(0)

    def make_default():
        constructor_call_count.value += 1
        return 0

    @idom.element
    async def Outer():
        update = idom.hooks.use_update()

        async def on_click(event):
            update()

        return idom.html.div(
            idom.html.button(
                {"onClick": on_click, "id": "outer"}, "update outer (rerun constructor)"
            ),
            Inner(),
        )

    @idom.element
    async def Inner():
        count, set_count = idom.hooks.use_state(make_default)

        async def on_click(event):
            set_count(count + 1)

        return idom.html.div(
            idom.html.button(
                {"onClick": on_click, "id": "inner"},
                "update inner with state constructor",
            ),
            idom.html.p({"id": "count-view"}, count),
        )

    display(Outer)

    outer = driver.find_element_by_id("outer")
    inner = driver.find_element_by_id("inner")
    count = driver.find_element_by_id("count-view")

    assert constructor_call_count.value == 1
    assert count.get_attribute("innerHTML") == "0"

    inner.click()

    assert constructor_call_count.value == 1
    assert count.get_attribute("innerHTML") == "1"

    outer.click()

    assert constructor_call_count.value == 2
    assert count.get_attribute("innerHTML") == "0"

    inner.click()

    assert constructor_call_count.value == 2
    assert count.get_attribute("innerHTML") == "1"


def test_simple_input(driver, display):
    message_var = idom.Var(None)

    @idom.element
    async def Input(message=None):
        message, set_message = idom.hooks.use_state(message)
        message_var.set(message)

        async def on_change(event):
            if event["value"] == "this is a test":
                set_message(event["value"])

        if message is None:
            return idom.html.input({"id": "input", "onChange": on_change})
        else:
            return idom.html.p({"id": "complete"}, ["Complete"])

    display(Input)

    button = driver.find_element_by_id("input")
    button.send_keys("this is a test")
    driver.find_element_by_id("complete")

    assert message_var.get() == "this is a test"


def test_use_update(driver, display, driver_wait):
    var = idom.Var(0)

    @idom.element
    async def SideEffectCounter():
        var.value += 1
        update = idom.hooks.use_update()

        async def on_click(event):
            update()

        return idom.html.button(
            {"onClick": on_click, "id": "button", "count": var.value},
            f"Click count: {var.value}",
        )

    display(SideEffectCounter)

    client_button = driver.find_element_by_id("button")
    driver_wait.until(lambda dvr: client_button.get_attribute("count") == "1")

    client_button.click()
    driver_wait.until(lambda dvr: client_button.get_attribute("count") == "2")

    client_button.click()
    driver_wait.until(lambda dvr: client_button.get_attribute("count") == "3")


def test_use_memo(display, driver, driver_wait):
    trigger_count = 0

    @idom.element
    async def ComponentWithMemo():
        location, set_location = idom.hooks.use_state(
            "left",
            # force update every time
            should_update=lambda new, old: True,
        )

        @idom.hooks.use_memo(location)
        def count():
            nonlocal trigger_count
            trigger_count += 1
            return trigger_count

        async def on_left_button_click(event):
            set_location("left")

        async def on_right_button_click(event):
            set_location("right")

        return idom.html.div(
            idom.html.button(
                {"onClick": on_left_button_click, "id": "left-button"}, "left button"
            ),
            idom.html.button(
                {"onClick": on_right_button_click, "id": "right-button"}, "right button"
            ),
            f"Memo trigger count: {count}",
        )

    display(ComponentWithMemo)  # initial render triggers: yes

    left_client_button = driver.find_element_by_id("left-button")
    right_client_button = driver.find_element_by_id("right-button")

    right_client_button.click()  # trigger: yes
    right_client_button.click()  # trigger: no
    right_client_button.click()  # trigger: no
    left_client_button.click()  # trigger: yes
    left_client_button.click()  # trigger: no
    right_client_button.click()  # trigger: yes

    driver_wait.until(lambda drv: trigger_count == 4)


def test_use_lru_cache(display, driver, driver_wait):
    calls = []

    def function_to_memoize(some_value):
        calls.append(some_value)
        return some_value

    @idom.element
    async def ComponentWithMemo():
        location, set_location = idom.hooks.use_state("left")
        memoized_func = idom.hooks.use_lru_cache(function_to_memoize, maxsize=2)
        last_memoized_location = memoized_func(location)

        async def on_left_button_click(event):
            set_location("left")

        async def on_center_button_click(event):
            set_location("center")

        async def on_right_button_click(event):
            set_location("right")

        return idom.html.div(
            idom.html.button(
                {"onClick": on_left_button_click, "id": "left-button"}, "left button"
            ),
            idom.html.button(
                {"onClick": on_center_button_click, "id": "center-button"},
                "center button",
            ),
            idom.html.button(
                {"onClick": on_right_button_click, "id": "right-button"}, "right button"
            ),
            f"Last triggered on click: {last_memoized_location}",
        )

    display(ComponentWithMemo)  # cache state (triggers): [left, None]

    left_client_button = driver.find_element_by_id("left-button")
    center_client_button = driver.find_element_by_id("center-button")
    right_client_button = driver.find_element_by_id("right-button")

    center_client_button.click()  # cache state (triggers): [center, left]
    left_client_button.click()  # cache state: [left, center]
    right_client_button.click()  # cache state (triggers): [right, left]
    center_client_button.click()  # cache state (triggers): [center, right]
    center_client_button.click()  # cache state: [center, right]

    driver_wait.until(lambda drv: calls == ["left", "center", "right", "center"])


def test_use_shared_state(driver, driver_wait, display):
    @idom.element
    async def Outer():
        shared_count = idom.hooks.Shared(0)
        reset = idom.hooks.use_update()

        async def on_click(event):
            reset()

        return idom.html.div(
            idom.html.button({"onClick": on_click, "id": "reset-button"}, "reset"),
            Inner(shared_count, "button-1"),
            Inner(shared_count, "button-2"),
        )

    @idom.element
    async def Inner(shared_count, button_id):
        count, set_count = idom.hooks.use_state(shared_count)

        async def on_click(event):
            set_count(count + 1)

        return idom.html.button(
            {"onClick": on_click, "id": button_id, "count": count},
            f"Current click count: {count}",
        )

    display(Outer)

    client_reset_button = driver.find_element_by_id("reset-button")
    client_button_1 = driver.find_element_by_id("button-1")
    client_button_2 = driver.find_element_by_id("button-2")

    client_button_1.click()
    assert driver_wait.until(lambda dvr: client_button_1.get_attribute("count") == "1")
    assert driver_wait.until(lambda dvr: client_button_2.get_attribute("count") == "1")

    client_button_2.click()
    assert driver_wait.until(lambda dvr: client_button_1.get_attribute("count") == "2")
    assert driver_wait.until(lambda dvr: client_button_2.get_attribute("count") == "2")

    client_reset_button.click()
    assert driver_wait.until(lambda dvr: client_button_1.get_attribute("count") == "0")
    assert driver_wait.until(lambda dvr: client_button_2.get_attribute("count") == "0")

    client_button_1.click()
    assert driver_wait.until(lambda dvr: client_button_1.get_attribute("count") == "1")
    assert driver_wait.until(lambda dvr: client_button_2.get_attribute("count") == "1")

    client_button_2.click()
    assert driver_wait.until(lambda dvr: client_button_1.get_attribute("count") == "2")
    assert driver_wait.until(lambda dvr: client_button_2.get_attribute("count") == "2")


def test_use_shared_should_update(driver, driver_wait, display):
    @idom.element
    async def MessageInput():
        shared_message = idom.hooks.Shared("initial message")

        async def on_change(event):
            shared_message.update(event["value"])

        return idom.html.div(
            idom.html.input({"onChange": on_change, "id": "message-input"}),
            MessageView(shared_message, "view-1"),
            MessageView(shared_message, "view-2"),
        )

    @idom.element
    async def MessageView(shared_message, view_id):
        message, set_message = idom.hooks.use_state(
            shared_message,
            should_update=lambda new, old: new == f"message for {view_id}",
        )
        return idom.html.p({"id": view_id}, message)

    display(MessageInput)

    client_message_input = driver.find_element_by_id("message-input")
    client_view_1 = driver.find_element_by_id("view-1")
    client_view_2 = driver.find_element_by_id("view-2")

    driver_wait.until(
        lambda d: client_view_1.get_attribute("innerHTML") == "initial message"
    )
    driver_wait.until(
        lambda d: client_view_2.get_attribute("innerHTML") == "initial message"
    )

    client_message_input.send_keys("message for view-1")
    client_message_input.clear()

    driver_wait.until(
        lambda d: client_view_1.get_attribute("innerHTML") == "message for view-1"
    )
    driver_wait.until(
        lambda d: client_view_2.get_attribute("innerHTML") == "initial message"
    )

    client_message_input.send_keys("message for view-2")
    client_message_input.clear()

    driver_wait.until(
        lambda d: client_view_1.get_attribute("innerHTML") == "message for view-1"
    )
    driver_wait.until(
        lambda d: client_view_2.get_attribute("innerHTML") == "message for view-2"
    )