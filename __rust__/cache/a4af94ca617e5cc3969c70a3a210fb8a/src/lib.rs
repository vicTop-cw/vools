use std::os::raw::*;

#[no_mangle]
pub extern "C" fn cached_func(x: c_long) -> c_long {
    x + 100
}
