
// #pragma once
// #include "SJF.h"

// void add_fun(SJF* this,Process* toinsert)
// {
//     Pri_Node* node = (Pri_Node*) malloc(sizeof(Pri_Node));
//     node->data = toinsert;
//     node->pri = toinsert->RT;
//     this->queue.insert(&(this->queue.start),node);
// }
// Process* deq_fun(SJF* this)
// {
//     Pri_Node* node = this->queue.dequeue(&(this->queue.start));
//     return node->data;
// }

// void run_fun(SJF* this)
// {
//     if(this->queue.is_empty(&(this->queue)))
//     {
//         return;
//     }
//     if(this->running->rem_time == 0)
//     {
//         //handle deleting process from PCB and switching to new process
//         this->running = this->deq(this);
//     }
// }