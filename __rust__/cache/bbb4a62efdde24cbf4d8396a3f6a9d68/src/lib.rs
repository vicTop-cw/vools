use std::os::raw::*;

#[no_mangle]
pub extern "C" fn bad_func(x: c_long) -> c_long {
    this is not valid rust code !!!
}
