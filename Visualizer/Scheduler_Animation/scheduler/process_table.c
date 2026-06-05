#pragma once
#include "headers.h"

struct ll_Node {
    PCB* data;
    struct ll_Node* next;
};

struct ll {
    struct ll_Node* head;
    void (*insert)(PCB* pcb);
    PCB* (*remove)(int id);
    PCB* (*update_pcb)(int id, int new_state, int rem_t);
};

struct ll process_table;

void insert(PCB* pcb) {
    struct ll_Node* new_node = (struct ll_Node*) malloc(sizeof(struct ll_Node));
    new_node->data = pcb;
    new_node->next = NULL;
    if(process_table.head == NULL)
        process_table.head = new_node;
    else
        {
            struct ll_Node* temp = process_table.head->next;
            process_table.head->next = new_node;
            new_node->next = temp;
        }
}

PCB* delete(int id) {
    if(process_table.head == NULL)
        return NULL;

    struct ll_Node* temp = NULL;
    struct ll_Node* current = process_table.head;
    if(current->data->id == id)
    {
        process_table.head = current->next;
        temp = current;
    } else {
        while(current->next != NULL && current->next->data->id != id)
            current = current->next;
        if (current->next != NULL)
        {
            temp = current->next;
            current->next = temp->next;
        }
    }
    PCB* data = temp->data; //could this line cause error if the temp is NULL?
    free(temp);
    return data;
}

PCB* update_pcb(int id, int new_state, int rem_t) {
    if(process_table.head == NULL)
        return NULL;

    struct ll_Node* current = process_table.head;
    while(current != NULL)
    {
        if (current->data->id == id)
        {
            current->data->state = new_state;
            current->data->ex_t += current->data->rem_t - rem_t;
            current->data->rem_t = rem_t;
            return current->data;
        }
        current = current->next;
    }
}

static void create_process_table()
{
    process_table.head = NULL;
    process_table.insert = &insert;
    process_table.remove = &delete;
    process_table.update_pcb = &update_pcb;
}