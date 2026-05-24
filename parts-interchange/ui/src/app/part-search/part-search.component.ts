import { SelectionModel } from '@angular/cdk/collections';
import { AfterViewInit, Component, EventEmitter, Inject, ViewChild } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialog } from '@angular/material/dialog';
import { MatPaginator } from '@angular/material/paginator';
import { MatSort } from '@angular/material/sort';
import { filter, map, merge, startWith, switchMap } from 'rxjs';
import { Message, MessageQueues, MessageService } from 'src/services/message.service';
import { PartsPageRequest, PartsService } from 'src/services/parts.service';
import { TreeService } from 'src/services/tree.service';

export interface Part {
  applications: string
  category_id: number
  condition: string
  description: string
  hazmat: string
  id: number
  manufacturer_id: number
  notes: string
  other_names: string
  part_number: string
  positions: string
  replaces: string
  sold_in_quantity: string
  title: string
  url: string
}

@Component({
  selector: 'app-part-search',
  templateUrl: './part-search.component.html',
  styleUrls: ['./part-search.component.scss'],
  providers: [TreeService, PartsService]
})
export class PartSearchComponent implements AfterViewInit {

  private car: any;
  parts: any = null;
  displayedColumns = ['sku', 'title', 'description', 'image']
  resultsLength = 0;
  filterStr = '';
  isLoadingResults = true;
  selection: SelectionModel<Part>;

  carId: number = 0;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;
  filterEmitter: EventEmitter<any>;

  constructor(private messageService: MessageService, public dialog: MatDialog, private partsService: PartsService) {
    this.selection = new SelectionModel<Part>(false, []);
    this.filterEmitter = new EventEmitter();

    this.messageService.getMessage().pipe(filter((event) => event.getQueue() == MessageQueues.CAR_PICKER_QUEUE)).subscribe((msg: any) => {
      if (msg.getPayload()) {
        this.carId = msg.getPayload()['id']
        this.filterEmitter.emit(msg);
        this.initializeTablePagingSorting();
      } else {
        // Reset called, do nothing
      }
    })
  }

  ngAfterViewInit(): void {
    // this.initializeTablePagingSorting();
  }

  initializeTablePagingSorting() {
    // When sort is changed, reset page index to 1
    this.sort.sortChange.subscribe(() => {
      this.paginator.pageIndex = 0;
    });

    merge(this.sort.sortChange, this.paginator.page, this.filterEmitter)
      .pipe(
        startWith({}),
        switchMap((val: any) => {
          this.isLoadingResults = true;
          console.log('called')
          if (val['type'] == 'filter') {
            this.paginator.pageIndex = 0;
            console.log('test')
          }
          return this.loadData(this.sort.active, this.sort.direction, this.paginator.pageIndex, this.paginator.pageSize, this.filterStr);
        }),
        map(data => {
          this.isLoadingResults = false;
          console.log('map')
          console.log(data)
          return data;
        })
      ).subscribe(data => {
        this.parts = data['items'];
        this.resultsLength = data['total']
      })
  }

  loadData(sortCol: string, sortDir: string, pageIndex: number, pageSize: number, filterStr: string) {
    let ppr = new PartsPageRequest(this.carId, pageIndex, pageSize, sortCol, sortDir, filterStr)
    return this.partsService.get_parts_paged(ppr);
  }

  partSelected(part: Part) {
    console.log(part)
    this.messageService.sendMessage(new Message(MessageQueues.PART_SEARCH_QUEUE, part))
  }

  filterUpdated(event: any) {
    console.log(event);
    this.filterEmitter.emit({'event': event, 'type': 'filter'})
  }

  openDialog(event: any) {
    console.log(event);
    this.dialog.open(DialogImgViewer, {
      width: '70%',
      data: event
    })
  }

}

@Component({
  selector: 'dialog-img-viewer',
  templateUrl: 'dialog-img-viewer.html',
  standalone: true
})
export default class DialogImgViewer {
  imgUrl: string;
  constructor( @Inject(MAT_DIALOG_DATA) public data: string ) {
    console.log(data)
    this.imgUrl = data;
  }
}