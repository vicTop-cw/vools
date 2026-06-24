use std::os::raw::*;

#[no_mangle]
pub extern "C" fn test_add(a: c_long, b: c_long) -> c_long {
    return a + b;
}
