//! vools_bridge_safe_eval - Rust-based secure expression evaluator
//!
//! A stack-based VM for executing pre-parsed safe expressions.
//! This module does NOT import any vools modules to avoid circular imports.

use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Maximum stack depth to prevent stack overflow attacks
const MAX_STACK_DEPTH: usize = 1000;
/// Maximum instruction count to prevent infinite loops
const MAX_INSTRUCTIONS: usize = 100000;
/// Maximum string length
const MAX_STRING_LEN: usize = 10000;

/// Value types supported in the VM
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Integer(i64),
    Float(f64),
    String(String),
    Boolean(bool),
}

/// Instruction opcodes
mod opcodes {
    pub const PUSH_INT: u8 = 0x01;
    pub const PUSH_FLOAT: u8 = 0x02;
    pub const PUSH_STR: u8 = 0x03;
    pub const PUSH_BOOL: u8 = 0x04;
    pub const LOAD_VAR: u8 = 0x05;
    pub const ADD: u8 = 0x10;
    pub const SUB: u8 = 0x11;
    pub const MUL: u8 = 0x12;
    pub const DIV: u8 = 0x13;
    pub const MOD: u8 = 0x14;
    pub const NEG: u8 = 0x15;
    pub const EQ: u8 = 0x20;
    pub const NE: u8 = 0x21;
    pub const LT: u8 = 0x22;
    pub const GT: u8 = 0x23;
    pub const LE: u8 = 0x24;
    pub const GE: u8 = 0x25;
    pub const AND: u8 = 0x30;
    pub const OR: u8 = 0x31;
    pub const NOT: u8 = 0x32;
    pub const END: u8 = 0xFF;
}

/// Evaluation error types
#[derive(Debug)]
pub enum EvalError {
    SyntaxError(String),
    DivByZero,
    TypeError(String),
    StackOverflow,
    Timeout,
    UnknownOpcode(u8),
    InsufficientStack,
}

/// Serialize a value to JSON string for return
fn value_to_json(v: &Value) -> String {
    match v {
        Value::Integer(i) => format!("{{\"type\":\"int\",\"value\":{}}}", i),
        Value::Float(f) => format!("{{\"type\":\"float\",\"value\":{}}}", f),
        Value::String(s) => format!("{{\"type\":\"str\",\"value\":{}}}", serde_json_str(s)),
        Value::Boolean(b) => format!("{{\"type\":\"bool\",\"value\":{}}}", if *b { "true" } else { "false" }),
    }
}

/// Serialize a string to JSON-safe string
fn serde_json_str(s: &str) -> String {
    let mut result = String::with_capacity(s.len() + 2);
    result.push('"');
    for c in s.chars() {
        match c {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            c if c.is_control() => {
                result.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => result.push(c),
        }
    }
    result.push('"');
    result
}

/// Execute instructions with timeout
pub fn eval_with_timeout(instructions: &[u8], timeout_ms: u64, vars: HashMap<String, Value>) -> Result<Value, EvalError> {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    eval_inner(instructions, &deadline, vars)
}

fn eval_inner(instructions: &[u8], deadline: &Instant, vars: HashMap<String, Value>) -> Result<Value, EvalError> {
    let mut stack: Vec<Value> = Vec::with_capacity(64);
    let mut pc: usize = 0;
    let mut instruction_count: usize = 0;

    while pc < instructions.len() {
        // Check timeout
        if Instant::now() >= *deadline {
            return Err(EvalError::Timeout);
        }

        // Check instruction count
        instruction_count += 1;
        if instruction_count > MAX_INSTRUCTIONS {
            return Err(EvalError::SyntaxError("Too many instructions".to_string()));
        }

        let opcode = instructions[pc];
        pc += 1;

        match opcode {
            opcodes::PUSH_INT => {
                if pc + 8 > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated PUSH_INT".to_string()));
                }
                let bytes: [u8; 8] = instructions[pc..pc + 8].try_into().unwrap();
                let val = i64::from_le_bytes(bytes);
                stack.push(Value::Integer(val));
                pc += 8;
            }
            opcodes::PUSH_FLOAT => {
                if pc + 8 > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated PUSH_FLOAT".to_string()));
                }
                let bytes: [u8; 8] = instructions[pc..pc + 8].try_into().unwrap();
                let val = f64::from_le_bytes(bytes);
                stack.push(Value::Float(val));
                pc += 8;
            }
            opcodes::PUSH_STR => {
                if pc + 4 > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated PUSH_STR".to_string()));
                }
                let bytes: [u8; 4] = instructions[pc..pc + 4].try_into().unwrap();
                let len = u32::from_le_bytes(bytes) as usize;
                pc += 4;
                if pc + len > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated PUSH_STR".to_string()));
                }
                if len > MAX_STRING_LEN {
                    return Err(EvalError::SyntaxError("String too long".to_string()));
                }
                let s = String::from_utf8(instructions[pc..pc + len].to_vec())
                    .map_err(|_| EvalError::SyntaxError("Invalid UTF-8".to_string()))?;
                stack.push(Value::String(s));
                pc += len;
            }
            opcodes::PUSH_BOOL => {
                if pc >= instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated PUSH_BOOL".to_string()));
                }
                let val = instructions[pc] != 0;
                stack.push(Value::Boolean(val));
                pc += 1;
            }
            opcodes::LOAD_VAR => {
                if pc + 4 > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated LOAD_VAR".to_string()));
                }
                let bytes: [u8; 4] = instructions[pc..pc + 4].try_into().unwrap();
                let len = u32::from_le_bytes(bytes) as usize;
                pc += 4;
                if pc + len > instructions.len() {
                    return Err(EvalError::SyntaxError("Truncated LOAD_VAR".to_string()));
                }
                let name = String::from_utf8(instructions[pc..pc + len].to_vec())
                    .map_err(|_| EvalError::SyntaxError("Invalid UTF-8".to_string()))?;
                pc += len;
                match vars.get(&name) {
                    Some(v) => stack.push(v.clone()),
                    None => return Err(EvalError::SyntaxError(format!("Unknown variable: {}", name))),
                }
            }
            opcodes::ADD => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Integer(a + b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Float(a + b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Float(a as f64 + b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Float(a + b as f64)),
                    (Value::String(a), Value::String(b)) => stack.push(Value::String(a + &b)),
                    _ => return Err(EvalError::TypeError("ADD: incompatible types".to_string())),
                }
            }
            opcodes::SUB => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Integer(a - b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Float(a - b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Float(a as f64 - b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Float(a - b as f64)),
                    _ => return Err(EvalError::TypeError("SUB: incompatible types".to_string())),
                }
            }
            opcodes::MUL => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Integer(a * b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Float(a * b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Float(a as f64 * b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Float(a * b as f64)),
                    _ => return Err(EvalError::TypeError("MUL: incompatible types".to_string())),
                }
            }
            opcodes::DIV => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => {
                        if b == 0 {
                            return Err(EvalError::DivByZero);
                        }
                        stack.push(Value::Integer(a / b));
                    }
                    (Value::Float(a), Value::Float(b)) => {
                        if b == 0.0 {
                            return Err(EvalError::DivByZero);
                        }
                        stack.push(Value::Float(a / b));
                    }
                    (Value::Integer(a), Value::Float(b)) => {
                        if b == 0.0 {
                            return Err(EvalError::DivByZero);
                        }
                        stack.push(Value::Float(a as f64 / b));
                    }
                    (Value::Float(a), Value::Integer(b)) => {
                        if b == 0 {
                            return Err(EvalError::DivByZero);
                        }
                        stack.push(Value::Float(a / b as f64));
                    }
                    _ => return Err(EvalError::TypeError("DIV: incompatible types".to_string())),
                }
            }
            opcodes::MOD => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => {
                        if b == 0 {
                            return Err(EvalError::DivByZero);
                        }
                        stack.push(Value::Integer(a % b));
                    }
                    _ => return Err(EvalError::TypeError("MOD: incompatible types".to_string())),
                }
            }
            opcodes::NEG => {
                if stack.len() < 1 {
                    return Err(EvalError::InsufficientStack);
                }
                let a = stack.pop().unwrap();
                match a {
                    Value::Integer(a) => stack.push(Value::Integer(-a)),
                    Value::Float(a) => stack.push(Value::Float(-a)),
                    _ => return Err(EvalError::TypeError("NEG: incompatible type".to_string())),
                }
            }
            opcodes::EQ => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                stack.push(Value::Boolean(a == b));
            }
            opcodes::NE => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                stack.push(Value::Boolean(a != b));
            }
            opcodes::LT => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Boolean(a < b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Boolean(a < b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Boolean((a as f64) < b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Boolean(a < (b as f64))),
                    _ => return Err(EvalError::TypeError("LT: incompatible types".to_string())),
                }
            }
            opcodes::GT => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Boolean(a > b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Boolean(a > b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Boolean((a as f64) > b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Boolean(a > (b as f64))),
                    _ => return Err(EvalError::TypeError("GT: incompatible types".to_string())),
                }
            }
            opcodes::LE => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Boolean(a <= b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Boolean(a <= b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Boolean((a as f64) <= b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Boolean(a <= (b as f64))),
                    _ => return Err(EvalError::TypeError("LE: incompatible types".to_string())),
                }
            }
            opcodes::GE => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (a, b) {
                    (Value::Integer(a), Value::Integer(b)) => stack.push(Value::Boolean(a >= b)),
                    (Value::Float(a), Value::Float(b)) => stack.push(Value::Boolean(a >= b)),
                    (Value::Integer(a), Value::Float(b)) => stack.push(Value::Boolean((a as f64) >= b)),
                    (Value::Float(a), Value::Integer(b)) => stack.push(Value::Boolean(a >= (b as f64))),
                    _ => return Err(EvalError::TypeError("GE: incompatible types".to_string())),
                }
            }
            opcodes::AND => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (&a, &b) {
                    (Value::Boolean(a), Value::Boolean(b)) => stack.push(Value::Boolean(*a && *b)),
                    _ => return Err(EvalError::TypeError("AND: requires booleans".to_string())),
                }
            }
            opcodes::OR => {
                if stack.len() < 2 {
                    return Err(EvalError::InsufficientStack);
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                match (&a, &b) {
                    (Value::Boolean(a), Value::Boolean(b)) => stack.push(Value::Boolean(*a || *b)),
                    _ => return Err(EvalError::TypeError("OR: requires booleans".to_string())),
                }
            }
            opcodes::NOT => {
                if stack.len() < 1 {
                    return Err(EvalError::InsufficientStack);
                }
                let a = stack.pop().unwrap();
                match a {
                    Value::Boolean(a) => stack.push(Value::Boolean(!a)),
                    _ => return Err(EvalError::TypeError("NOT: requires boolean".to_string())),
                }
            }
            opcodes::END => {
                break;
            }
            _ => return Err(EvalError::UnknownOpcode(opcode)),
        }

        // Check stack depth
        if stack.len() > MAX_STACK_DEPTH {
            return Err(EvalError::StackOverflow);
        }
    }

    stack.pop().ok_or_else(|| EvalError::SyntaxError("Empty stack".to_string()))
}

/// Convert error to JSON string
fn error_to_json(e: &EvalError) -> String {
    match e {
        EvalError::SyntaxError(msg) => format!("{{\"error\":\"syntax\",\"message\":{}}}", serde_json_str(msg)),
        EvalError::DivByZero => format!("{{\"error\":\"divzero\",\"message\":{}}}", serde_json_str("Division by zero")),
        EvalError::TypeError(msg) => format!("{{\"error\":\"type\",\"message\":{}}}", serde_json_str(msg)),
        EvalError::StackOverflow => format!("{{\"error\":\"overflow\",\"message\":{}}}", serde_json_str("Stack overflow")),
        EvalError::Timeout => format!("{{\"error\":\"timeout\",\"message\":{}}}", serde_json_str("Execution timeout")),
        EvalError::UnknownOpcode(op) => format!("{{\"error\":\"opcode\",\"message\":{}}}", serde_json_str(&format!("Unknown opcode: {}", op))),
        EvalError::InsufficientStack => format!("{{\"error\":\"stack\",\"message\":{}}}", serde_json_str("Insufficient stack")),
    }
}

/// Main FFI function: eval(instructions: *const u8, len: usize, timeout_ms: u32) -> *mut u8
/// Returns a pointer to a JSON string that must be freed by the caller.
/// The returned string format: {"ok": true, "value": {...}} or {"ok": false, "error": {...}}
#[no_mangle]
pub extern "C" fn eval(instructions: *const u8, len: usize, timeout_ms: u32) -> *mut u8 {
    if instructions.is_null() || len == 0 {
        let result = format!("{{\"ok\":false,\"error\":{}}}", error_to_json(&EvalError::SyntaxError("Null instructions".to_string())));
        return allocate_string(result);
    }

    let instr_slice = unsafe { std::slice::from_raw_parts(instructions, len) };
    let vars = HashMap::new(); // Empty vars for simple eval

    match eval_with_timeout(instr_slice, timeout_ms as u64, vars) {
        Ok(v) => {
            let result = format!("{{\"ok\":true,\"value\":{}}}", value_to_json(&v));
            allocate_string(result)
        }
        Err(e) => {
            let result = format!("{{\"ok\":false,\"error\":{}}}", error_to_json(&e));
            allocate_string(result)
        }
    }
}

/// Allocate a string in the heap and return a pointer to it
/// Uses libc malloc for compatibility with ctypes
fn allocate_string(s: String) -> *mut u8 {
    let bytes = s.into_bytes();
    let len = bytes.len();
    let total_size = len + 1;
    let ptr = unsafe { libc::malloc(total_size) } as *mut u8;
    if ptr.is_null() {
        return ptr;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), ptr, len);
        *ptr.add(len) = 0;
    }
    ptr
}

/// Free a string allocated by allocate_string
#[no_mangle]
pub extern "C" fn free_result(ptr: *mut u8) {
    if !ptr.is_null() {
        unsafe {
            libc::free(ptr as *mut libc::c_void);
        }
    }
}
