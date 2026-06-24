use std::os::raw::*;

#[no_mangle]
pub extern "C" fn fib(n: c_long) -> c_long {
    if n <= 1 {
                    1
                } else {
                    fib(n - 1) + fib(n - 2)
                }
}
