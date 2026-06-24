use std::os::raw::*;

#[no_mangle]
pub extern "C" fn async_debug_func(x: c_long) -> c_long {
    <coroutine object TestRustAsyncModes.test_async_debug_mode.<locals>.async_debug_func at 0x000001DD16C5AD40>
}
