#pragma once
#define ATOMIC_RESTORESTATE 0
// Single-threaded host harness: execute the block once. No emulated locking.
#define ATOMIC_BLOCK(state) if (true)
