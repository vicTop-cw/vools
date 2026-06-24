use std::os::raw::*;

#[no_mangle]
pub extern "C" fn add(a: c_long, b: c_long) -> c_long {
    a + b
}
