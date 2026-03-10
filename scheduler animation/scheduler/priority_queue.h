
#pragma once
#include "headers.h"

typedef struct pri_node {
    int pri;
    Process* data;
    struct pri_node* next;
} Pri_Node;

typedef struct pri_queue {
    Pri_Node* start;
    void (*insert)(Pri_Node**,Pri_Node*);
    Pri_Node* (*dequeue)(Pri_Node**);
    bool (*is_empty)(struct pri_queue*);
    void(*print)(Pri_Node*);
}Pri_Queue;

void print_queue(Pri_Node* start)
{
    Pri_Node* curr = start;
    while(curr != NULL)
    {
        printf("(Process: %d)->",curr->data->Id);
        curr = curr->next;
    }
    printf("NULL\n");
}

void insert_fun(Pri_Node** start,Pri_Node* toinsert)
{
    if(*start == NULL)
    {
        *start = toinsert;
         toinsert->next = NULL;
        return;
    }
    if(toinsert->pri < (*start)->pri)
    {
        toinsert->next = *start;
        *start = toinsert;
        return;
    }
    Pri_Node* current = *start;
    bool flag = false;
    while(current->next != NULL)
    {
        if(toinsert->pri < current->next->pri)
        {
            toinsert->next = current->next;
            current->next = toinsert;
            flag = true;
            break;
        }
        current = current->next;
    }
    if(!flag)
    {
        current->next = toinsert;
        toinsert->next = NULL;
    }
    return;
}

Pri_Node* dequeue_fun(Pri_Node** start)
{
    if(*start == NULL)
        return NULL;
    Pri_Node* temp = *start;
    *start = temp->next;
    return temp;
}

bool is_empty_fun(Pri_Queue* this)
{
    if(this->start == NULL)
        return true;
    else
        return false;
}

Pri_Queue default_pri_queue;

static void create_default_pq()
{
    Pri_Queue q;
    default_pri_queue.start = NULL;
    default_pri_queue.insert = &insert_fun;
    default_pri_queue.dequeue = &dequeue_fun;
    default_pri_queue.is_empty = &is_empty_fun;
    default_pri_queue.print = &print_queue;
}
