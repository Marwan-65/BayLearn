
// #include "priority_queue.h"

// void insert_fun(Pri_Node** start,Pri_Node* toinsert)
// {
//     if(*start == NULL)
//     {
//         *start = toinsert;
//         return;
//     }
//     if(toinsert->pri < (*start)->pri)
//     {
//         toinsert->next = *start;
//         *start = toinsert;
//         return;
//     }
//     Pri_Node* current = *start;
//     bool flag = false;
//     while(current->next != NULL)
//     {
//         if(toinsert->pri < current->next->pri)
//         {
//             toinsert->next = current->next;
//             current->next = toinsert;
//             flag = true;
//             break;
//         }
//         current = current->next;
//     }
//     if(!flag)
//     {
//         current->next = toinsert;
//     }
//     return;
// }

// Pri_Node* dequeue_fun(Pri_Node** start)
// {
//     Pri_Node* temp = *start;
//     *start = temp->next;
//     return temp;
// }

// bool is_empty_fun(Pri_Queue* this)
// {
//     if(this->start == NULL)
//         return true;
//     else
//         return false;
// }